import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.helpers.dto import ParsedEmail
from app.helpers.enums import EmailCategoryEnum, LanguageEnum
from app.services.classifier import (
    RETRY_USER_LINE,
    REVIEW_PROMPT,
    SYSTEM_PROMPT,
    UKRAINIAN_INSTRUCTION,
    build_classify_tool,
    classify_email,
    cyrillic_ratio,
    get_client,
    is_ukrainian,
)

PARSED = ParsedEmail(
    sender="sender@example.com",
    to="to@example.com",
    subject="s",
    date="d",
    body="b",
)

UK_REASONING = "Лист містить ознаки фішингу."
EN_REASONING = "The email shows signs of phishing."


def _mock_response(category, confidence, reasoning="r", signals=None):
    args = json.dumps({
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
        "signals": signals or [],
    })
    tc = MagicMock()
    tc.function.arguments = args
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[tc]))])


class TestClassifyEmail:
    async def test_high_confidence_no_review(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                return_value=_mock_response("spam", 0.95, "because tests", ["bad-link"])
            )

            result = await classify_email(PARSED)

            assert result.category == EmailCategoryEnum.SPAM
            assert result.confidence == 0.95
            assert result.reasoning == "because tests"
            assert result.signals == ["bad-link"]
            assert result.reviewed is False
            assert mock_instance.chat.completions.create.call_count == 1

    async def test_low_confidence_triggers_review(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("newsletter", 0.5),
                    _mock_response("phishing", 0.92, "after review", ["red flag"]),
                ]
            )

            result = await classify_email(PARSED)

            assert result.category == EmailCategoryEnum.PHISHING
            assert result.confidence == 0.92
            assert result.reasoning == "after review"
            assert result.signals == ["red flag"]
            assert result.reviewed is True
            assert mock_instance.chat.completions.create.call_count == 2

    async def test_confidence_at_threshold_triggers_review(self):
        # Default threshold is 0.85; <= triggers review.
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("transactional", 0.85),
                    _mock_response("personal", 0.99),
                ]
            )

            result = await classify_email(PARSED)

            assert result.reviewed is True
            assert result.category == EmailCategoryEnum.PERSONAL

    async def test_no_tool_call_raises(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_resp = MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=None))])
            mock_instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            with pytest.raises(RuntimeError, match="did not return a tool call"):
                await classify_email(PARSED)


class TestLanguage:
    async def test_default_prompt_has_no_language_instruction(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(return_value=_mock_response("spam", 0.95))

            await classify_email(PARSED)

            prompt = mock_instance.chat.completions.create.call_args.kwargs["messages"][0]["content"]
            assert prompt == SYSTEM_PROMPT

    async def test_ukrainian_instruction_leads_the_prompt(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                return_value=_mock_response("spam", 0.95, UK_REASONING)
            )

            await classify_email(PARSED, LanguageEnum.UK)

            prompt = mock_instance.chat.completions.create.call_args.kwargs["messages"][0]["content"]
            assert prompt.startswith(UKRAINIAN_INSTRUCTION)
            assert prompt.endswith(SYSTEM_PROMPT)

    async def test_review_pass_also_leads_with_the_instruction(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("newsletter", 0.5, UK_REASONING),
                    _mock_response("phishing", 0.92, UK_REASONING),
                ]
            )

            await classify_email(PARSED, LanguageEnum.UK)

            prompts = [
                call.kwargs["messages"][0]["content"]
                for call in mock_instance.chat.completions.create.call_args_list
            ]
            assert prompts[1].startswith(UKRAINIAN_INSTRUCTION)
            assert prompts[1].endswith(REVIEW_PROMPT)
            assert all(prompt.startswith(UKRAINIAN_INSTRUCTION) for prompt in prompts)


class TestClassifyToolSchema:
    def _fields(self, language):
        properties = build_classify_tool(language)["function"]["parameters"]["properties"]
        return properties["reasoning"]["description"], properties["signals"]["items"]["description"]

    def test_uk_marks_reasoning_and_signal_items(self):
        reasoning, signal_item = self._fields(LanguageEnum.UK)

        assert "Ukrainian" in reasoning
        assert "Ukrainian" in signal_item

    def test_en_leaves_the_descriptions_alone(self):
        reasoning, signal_item = self._fields(LanguageEnum.EN)

        assert "Ukrainian" not in reasoning
        assert "Ukrainian" not in signal_item

    def test_category_enum_is_unchanged_by_language(self):
        for language in (LanguageEnum.EN, LanguageEnum.UK):
            properties = build_classify_tool(language)["function"]["parameters"]["properties"]
            assert properties["category"]["enum"] == [e.value for e in EmailCategoryEnum]


class TestCyrillicCheck:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Лист містить ознаки фішингу", 1.0),
            ("The email shows signs of phishing", 0.0),
            ("", 0.0),
            ("123 — !!! ...", 0.0),
        ],
    )
    def test_ratio(self, text, expected):
        assert cyrillic_ratio(text) == expected

    def test_ukrainian_only_letters_count_as_cyrillic(self):
        assert cyrillic_ratio("їжак єнот ґанок і") == 1.0

    def test_mixed_text_is_still_ukrainian(self):
        # A Latin acronym inside Ukrainian prose must not tip the verdict.
        assert is_ukrainian("Посилання веде на зовнішній домен IT-відділу")

    def test_half_and_half_passes_at_the_threshold(self):
        assert is_ukrainian("абвг abcd")

    def test_english_is_rejected(self):
        assert not is_ukrainian(EN_REASONING)

    def test_empty_is_rejected(self):
        assert not is_ukrainian("")


class TestLanguageRetry:
    async def test_english_answer_is_retried_once(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("phishing", 0.95, EN_REASONING),
                    _mock_response("phishing", 0.95, UK_REASONING, ["зовнішній домен"]),
                ]
            )

            result = await classify_email(PARSED, LanguageEnum.UK)

            assert mock_instance.chat.completions.create.call_count == 2
            assert result.reasoning == UK_REASONING
            assert result.signals == ["зовнішній домен"]
            assert result.reviewed is False

            retry_message = mock_instance.chat.completions.create.call_args.kwargs["messages"][1]["content"]
            assert retry_message.endswith(RETRY_USER_LINE)

    async def test_ukrainian_answer_is_not_retried(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                return_value=_mock_response("phishing", 0.95, UK_REASONING)
            )

            await classify_email(PARSED, LanguageEnum.UK)

            assert mock_instance.chat.completions.create.call_count == 1

    async def test_english_request_is_never_retried(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                return_value=_mock_response("phishing", 0.95, EN_REASONING)
            )

            await classify_email(PARSED)

            assert mock_instance.chat.completions.create.call_count == 1

    async def test_second_miss_is_kept_and_logged(self, caplog):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                return_value=_mock_response("phishing", 0.95, EN_REASONING)
            )

            with caplog.at_level(logging.WARNING, logger="app.services.classifier"):
                result = await classify_email(PARSED, LanguageEnum.UK)

            assert mock_instance.chat.completions.create.call_count == 2
            assert result.reasoning == EN_REASONING
            assert "still did not answer in Ukrainian" in caplog.text

    async def test_retry_runs_per_pass(self):
        # Low confidence first: the review pass gets its own guard and its own retry.
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("newsletter", 0.5, EN_REASONING),
                    _mock_response("newsletter", 0.5, UK_REASONING),
                    _mock_response("phishing", 0.93, EN_REASONING),
                    _mock_response("phishing", 0.93, UK_REASONING),
                ]
            )

            result = await classify_email(PARSED, LanguageEnum.UK)

            assert mock_instance.chat.completions.create.call_count == 4
            assert result.reviewed is True
            assert result.reasoning == UK_REASONING


class TestGetClient:
    def test_client_is_created_once_and_reused(self):
        get_client.cache_clear()
        try:
            with patch("app.services.classifier.AsyncOpenAI") as mock_client_class:
                first = get_client()
                second = get_client()

            assert first is second
            assert mock_client_class.call_count == 1
        finally:
            get_client.cache_clear()
