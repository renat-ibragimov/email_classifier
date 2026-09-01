import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.helpers.dto import ParsedEmail
from app.helpers.enums import EmailCategoryEnum, LanguageEnum
from app.services.classifier import REVIEW_PROMPT, SYSTEM_PROMPT, classify_email, get_client

PARSED = ParsedEmail(
    sender="sender@example.com",
    to="to@example.com",
    subject="s",
    date="d",
    body="b",
)


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

    async def test_ukrainian_instruction_is_appended(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(return_value=_mock_response("spam", 0.95))

            await classify_email(PARSED, LanguageEnum.UK)

            prompt = mock_instance.chat.completions.create.call_args.kwargs["messages"][0]["content"]
            assert prompt.startswith(SYSTEM_PROMPT)
            assert "in Ukrainian" in prompt

    async def test_review_pass_also_gets_the_instruction(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[_mock_response("newsletter", 0.5), _mock_response("phishing", 0.92)]
            )

            await classify_email(PARSED, LanguageEnum.UK)

            prompts = [
                call.kwargs["messages"][0]["content"]
                for call in mock_instance.chat.completions.create.call_args_list
            ]
            assert prompts[1].startswith(REVIEW_PROMPT)
            assert all("in Ukrainian" in prompt for prompt in prompts)


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
