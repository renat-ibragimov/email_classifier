from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.helpers.enums import LanguageEnum
from bot import language as language_store
from bot.api import InvalidEmailError, RateLimitedError, ServiceUnavailableError
from bot.handlers import (
    MAX_DOCUMENT_BYTES,
    handle_anything_else,
    handle_document,
    handle_help,
    handle_lang,
    handle_text,
)
from bot.i18n import t

USER_ID = 42
PAYLOAD = {"category": "phishing", "confidence": 0.9, "reasoning": "why", "signals": ["a"], "reviewed": False}


@pytest.fixture(autouse=True)
def clean_preferences():
    language_store.reset()
    yield
    language_store.reset()


class FakeMessage:
    """Stands in for aiogram's Message with only what the handlers touch."""

    def __init__(self, text=None, document=None, user_id=USER_ID, language_code=None):
        self.text = text
        self.caption = None
        self.document = document
        self.chat = SimpleNamespace(id=1)
        self.from_user = (
            SimpleNamespace(id=user_id, language_code=language_code) if user_id is not None else None
        )
        self.date = None
        self.forward_origin = None
        self.answer = AsyncMock()
        self.bot = SimpleNamespace(
            send_chat_action=AsyncMock(),
            download=AsyncMock(),
            set_my_commands=AsyncMock(),
        )

    @property
    def replies(self):
        return [call.args[0] for call in self.answer.await_args_list]


def _document(name="mail.eml", size=1024):
    return SimpleNamespace(file_name=name, file_size=size, file_id="doc-1")


def _client(outcome=None, error=None):
    client = AsyncMock()
    client.classify = AsyncMock(side_effect=error) if error else AsyncMock(return_value=outcome)
    return client


def _outcome(is_duplicate=False):
    return SimpleNamespace(payload=PAYLOAD, is_duplicate=is_duplicate)


class TestCommands:
    async def test_help_defaults_to_english(self):
        message = FakeMessage()

        await handle_help(message)

        assert message.replies == [t(LanguageEnum.EN, "help")]

    async def test_the_first_reply_follows_the_telegram_client(self):
        for code in ("uk", "ru", "uk-UA"):
            message = FakeMessage(language_code=code)

            await handle_help(message)

            assert message.replies == [t(LanguageEnum.UK, "help")]

    async def test_an_unsupported_client_language_gets_english(self):
        message = FakeMessage(language_code="de")

        await handle_help(message)

        assert message.replies == [t(LanguageEnum.EN, "help")]

    async def test_lang_toggles_away_from_the_detected_language(self):
        message = FakeMessage()

        await handle_lang(message)

        assert message.replies == [t(LanguageEnum.UK, "language_set")]
        assert language_store.stored_language(USER_ID) is LanguageEnum.UK

    async def test_lang_toggles_away_from_a_ukrainian_client(self):
        message = FakeMessage(language_code="ru")

        await handle_lang(message)

        assert language_store.stored_language(USER_ID) is LanguageEnum.EN

    async def test_lang_republishes_the_menu_in_the_new_language(self):
        message = FakeMessage()

        await handle_lang(message)

        commands = message.bot.set_my_commands.await_args.args[0]
        assert [command.description for command in commands] == [
            t(LanguageEnum.UK, "cmd_help"),
            t(LanguageEnum.UK, "cmd_lang"),
        ]

    async def test_lang_toggles_back(self):
        message = FakeMessage()

        await handle_lang(message)
        await handle_lang(message)

        assert language_store.stored_language(USER_ID) is LanguageEnum.EN

    async def test_a_chosen_language_outranks_the_client(self):
        message = FakeMessage(language_code="uk")
        language_store.set_language(USER_ID, LanguageEnum.EN)

        await handle_help(message)

        assert message.replies == [t(LanguageEnum.EN, "help")]

    async def test_lang_ignores_a_message_without_a_sender(self):
        message = FakeMessage(user_id=None)

        await handle_lang(message)

        assert message.replies == []
        message.bot.set_my_commands.assert_not_awaited()

    async def test_lang_still_answers_when_the_menu_cannot_be_updated(self):
        message = FakeMessage()
        message.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("telegram is down"))

        await handle_lang(message)

        assert message.replies == [t(LanguageEnum.UK, "language_set")]


class TestText:
    async def test_classifies_and_answers_with_a_card(self):
        message = FakeMessage(text="Urgent: verify your account")
        client = _client(_outcome())

        await handle_text(message, client)

        assert client.classify.await_count == 1
        eml, language = client.classify.await_args.args
        assert b"Subject: Urgent: verify your account" in eml
        assert language is LanguageEnum.EN
        assert "FLAGGED" in message.replies[0]

    async def test_the_api_is_asked_in_the_client_language(self):
        message = FakeMessage(text="Urgent: verify your account", language_code="ru")
        client = _client(_outcome())

        await handle_text(message, client)

        assert client.classify.await_args.args[1] is LanguageEnum.UK
        assert "ЗАГРОЗА" in message.replies[0]

    async def test_shows_the_typing_action(self):
        message = FakeMessage(text="hello")

        await handle_text(message, _client(_outcome()))

        assert message.bot.send_chat_action.await_count == 1

    async def test_duplicate_adds_the_stored_result_line(self):
        message = FakeMessage(text="hello")

        await handle_text(message, _client(_outcome(is_duplicate=True)))

        assert "Already classified earlier" in message.replies[0]

    async def test_blank_text_is_rejected_before_the_api(self):
        message = FakeMessage(text="   \n  ")
        client = _client(_outcome())

        await handle_text(message, client)

        client.classify.assert_not_awaited()
        assert message.replies == [t(LanguageEnum.EN, "empty_text")]


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("error", "key"),
        [
            (InvalidEmailError(), "error_invalid"),
            (RateLimitedError(), "error_rate_limited"),
            (ServiceUnavailableError(), "error_unavailable"),
        ],
    )
    async def test_each_error_gets_its_own_line(self, error, key):
        message = FakeMessage(text="hello")

        await handle_text(message, _client(error=error))

        assert message.replies == [t(LanguageEnum.EN, key)]

    async def test_errors_are_localized(self):
        message = FakeMessage(text="hello")
        language_store.set_language(USER_ID, LanguageEnum.EN)

        await handle_text(message, _client(error=RateLimitedError()))

        assert message.replies == [t(LanguageEnum.EN, "error_rate_limited")]

    async def test_exception_text_never_reaches_the_user(self):
        message = FakeMessage(text="hello")

        await handle_text(message, _client(error=ServiceUnavailableError("connection refused to 10.0.0.1")))

        assert "10.0.0.1" not in message.replies[0]


class TestDocument:
    async def test_eml_is_downloaded_and_classified(self):
        message = FakeMessage(document=_document())
        message.bot.download = AsyncMock(return_value=SimpleNamespace(read=lambda: b"From: a@b.com\r\n\r\nbody\r\n"))
        client = _client(_outcome())

        await handle_document(message, client)

        assert client.classify.await_args.args[0] == b"From: a@b.com\r\n\r\nbody\r\n"
        assert "FLAGGED" in message.replies[0]

    async def test_non_eml_gets_the_hint(self):
        message = FakeMessage(document=_document(name="report.pdf"))
        client = _client(_outcome())

        await handle_document(message, client)

        client.classify.assert_not_awaited()
        assert message.replies == [t(LanguageEnum.EN, "hint")]

    async def test_oversized_file_is_refused(self):
        message = FakeMessage(document=_document(size=MAX_DOCUMENT_BYTES + 1))
        client = _client(_outcome())

        await handle_document(message, client)

        client.classify.assert_not_awaited()
        assert message.replies == [t(LanguageEnum.EN, "file_too_large")]

    async def test_file_at_the_limit_is_accepted(self):
        message = FakeMessage(document=_document(size=MAX_DOCUMENT_BYTES))
        message.bot.download = AsyncMock(return_value=SimpleNamespace(read=lambda: b"From: a@b.com\r\n\r\nx\r\n"))
        client = _client(_outcome())

        await handle_document(message, client)

        client.classify.assert_awaited_once()

    async def test_extension_check_is_case_insensitive(self):
        message = FakeMessage(document=_document(name="Mail.EML"))
        message.bot.download = AsyncMock(return_value=SimpleNamespace(read=lambda: b"From: a@b.com\r\n\r\nx\r\n"))
        client = _client(_outcome())

        await handle_document(message, client)

        client.classify.assert_awaited_once()

    async def test_failed_download_is_reported_as_unavailable(self):
        message = FakeMessage(document=_document())
        message.bot.download = AsyncMock(side_effect=RuntimeError("telegram is down"))
        client = _client(_outcome())

        await handle_document(message, client)

        client.classify.assert_not_awaited()
        assert message.replies == [t(LanguageEnum.EN, "error_unavailable")]
        assert "telegram is down" not in message.replies[0]


class TestFallback:
    async def test_other_messages_get_a_hint(self):
        message = FakeMessage()

        await handle_anything_else(message)

        assert message.replies == [t(LanguageEnum.EN, "hint")]
