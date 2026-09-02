from unittest.mock import AsyncMock

from aiogram.types import BotCommandScopeAllPrivateChats, BotCommandScopeChat

from app.helpers.enums import LanguageEnum
from bot.i18n import TEXTS, t
from bot.language import DEFAULT_LANGUAGE, UKRAINIAN_CLIENT_CODES
from bot.menu import MENU_COMMANDS, commands_for, set_chat_menu, set_default_menu

CHAT_ID = 777


def _bot():
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock()
    return bot


class TestCommandList:
    def test_menu_holds_help_and_lang_in_order(self):
        assert [command.command for command in commands_for(LanguageEnum.UK)] == ["help", "lang"]

    def test_descriptions_are_localized(self):
        assert commands_for(LanguageEnum.EN)[0].description == t(LanguageEnum.EN, "cmd_help")
        assert commands_for(LanguageEnum.UK)[0].description == t(LanguageEnum.UK, "cmd_help")

    def test_every_menu_key_is_translated(self):
        for table in TEXTS.values():
            assert all(key in table for _, key in MENU_COMMANDS)


class TestDefaultMenu:
    async def test_ukrainian_clients_get_the_ukrainian_menu(self):
        bot = _bot()

        await set_default_menu(bot)

        published = {
            call.kwargs["language_code"]: call.args[0]
            for call in bot.set_my_commands.await_args_list
            if call.kwargs.get("language_code")
        }
        assert set(published) == set(UKRAINIAN_CLIENT_CODES)
        assert all(commands == commands_for(LanguageEnum.UK) for commands in published.values())

    async def test_everyone_else_gets_the_untranslated_default(self):
        bot = _bot()

        await set_default_menu(bot)

        last = bot.set_my_commands.await_args
        assert last.kwargs.get("language_code") is None
        assert last.args[0] == commands_for(DEFAULT_LANGUAGE)

    async def test_the_default_menu_is_english(self):
        assert DEFAULT_LANGUAGE is LanguageEnum.EN

    async def test_targets_private_chats(self):
        bot = _bot()

        await set_default_menu(bot)

        for call in bot.set_my_commands.await_args_list:
            assert isinstance(call.kwargs["scope"], BotCommandScopeAllPrivateChats)


class TestChatMenu:
    async def test_scopes_the_menu_to_one_chat(self):
        bot = _bot()

        await set_chat_menu(bot, CHAT_ID, LanguageEnum.EN)

        scope = bot.set_my_commands.await_args.kwargs["scope"]
        assert isinstance(scope, BotCommandScopeChat)
        assert scope.chat_id == CHAT_ID

    async def test_uses_the_requested_language(self):
        bot = _bot()

        await set_chat_menu(bot, CHAT_ID, LanguageEnum.EN)

        assert bot.set_my_commands.await_args.args[0] == commands_for(LanguageEnum.EN)

    async def test_a_telegram_failure_is_swallowed(self):
        bot = _bot()
        bot.set_my_commands = AsyncMock(side_effect=RuntimeError("telegram is down"))

        await set_chat_menu(bot, CHAT_ID, LanguageEnum.UK)

    async def test_a_failure_is_logged(self, caplog):
        bot = _bot()
        bot.set_my_commands = AsyncMock(side_effect=RuntimeError("telegram is down"))

        with caplog.at_level("WARNING"):
            await set_chat_menu(bot, CHAT_ID, LanguageEnum.UK)

        assert str(CHAT_ID) in caplog.text
