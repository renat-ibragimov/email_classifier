import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.helpers.dto import ParsedEmail
from app.helpers.enums import EmailCategoryEnum
from app.services.classifier import classify_email

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
        with patch("app.services.classifier.AsyncOpenAI") as mock_client_class:
            mock_instance = mock_client_class.return_value
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
        with patch("app.services.classifier.AsyncOpenAI") as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.chat.completions.create = AsyncMock(side_effect=[
                _mock_response("newsletter", 0.5),
                _mock_response("phishing", 0.92, "after review", ["red flag"]),
            ])

            result = await classify_email(PARSED)

            assert result.category == EmailCategoryEnum.PHISHING
            assert result.confidence == 0.92
            assert result.reasoning == "after review"
            assert result.signals == ["red flag"]
            assert result.reviewed is True
            assert mock_instance.chat.completions.create.call_count == 2

    async def test_confidence_at_threshold_triggers_review(self):
        # Default threshold is 0.85; <= triggers review.
        with patch("app.services.classifier.AsyncOpenAI") as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.chat.completions.create = AsyncMock(side_effect=[
                _mock_response("transactional", 0.85),
                _mock_response("personal", 0.99),
            ])

            result = await classify_email(PARSED)

            assert result.reviewed is True
            assert result.category == EmailCategoryEnum.PERSONAL

    async def test_no_tool_call_raises(self):
        with patch("app.services.classifier.AsyncOpenAI") as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_resp = MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=None))])
            mock_instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            with pytest.raises(RuntimeError, match="did not return a tool call"):
                await classify_email(PARSED)
