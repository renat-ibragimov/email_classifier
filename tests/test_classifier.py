import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.helpers.dto import ParsedEmail
from app.helpers.enums import EmailCategoryEnum, LanguageEnum
from app.services.classifier import (
    HIGH_RISK_CUES,
    REVIEW_PROMPT,
    SYSTEM_PROMPT,
    classify_email,
    get_client,
    has_high_risk_cues,
    translate_result,
)

PARSED = ParsedEmail(
    sender="sender@example.com",
    to="to@example.com",
    subject="s",
    date="d",
    body="b",
)

RISKY = ParsedEmail(
    sender="it@corp-services.example.com",
    to="staff@example.com",
    subject="Password policy update",
    date="d",
    body="Follow the link to reset your credentials.",
)

EN_REASONING = "The email shows signs of phishing."
UK_REASONING = "Лист містить ознаки фішингу."


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


def _translation_response(reasoning, signals):
    tc = MagicMock()
    tc.function.arguments = json.dumps({"reasoning": reasoning, "signals": signals})
    return MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=[tc]))])


def _prompts(mock_create):
    return [call.kwargs["messages"][0]["content"] for call in mock_create.call_args_list]


def _tool_names(mock_create):
    return [call.kwargs["tools"][0]["function"]["name"] for call in mock_create.call_args_list]


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

    async def test_every_call_is_deterministic(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("newsletter", 0.5, EN_REASONING, ["a"]),
                    _mock_response("phishing", 0.92, EN_REASONING, ["a"]),
                    _translation_response(UK_REASONING, ["а"]),
                ]
            )

            await classify_email(PARSED, LanguageEnum.UK)

            temperatures = [
                call.kwargs["temperature"] for call in mock_instance.chat.completions.create.call_args_list
            ]
            assert temperatures == [0, 0, 0]


class TestAnalysisLanguage:
    async def test_english_prompts_carry_no_language_instruction(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(return_value=_mock_response("spam", 0.95))

            await classify_email(PARSED)

            assert _prompts(mock_instance.chat.completions.create) == [SYSTEM_PROMPT]

    async def test_uk_analysis_prompts_are_identical_to_english(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("newsletter", 0.5, EN_REASONING, ["a"]),
                    _mock_response("phishing", 0.92, EN_REASONING, ["a"]),
                    _translation_response(UK_REASONING, ["б"]),
                ]
            )

            await classify_email(PARSED, LanguageEnum.UK)

            analysis_prompts = _prompts(mock_instance.chat.completions.create)[:2]
            assert analysis_prompts == [SYSTEM_PROMPT, REVIEW_PROMPT]
            assert all("Ukrainian" not in prompt for prompt in analysis_prompts)

    async def test_analysis_tool_schema_never_mentions_ukrainian(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("spam", 0.95, EN_REASONING, ["a"]),
                    _translation_response(UK_REASONING, ["в"]),
                ]
            )

            await classify_email(PARSED, LanguageEnum.UK)

            analysis_tool = mock_instance.chat.completions.create.call_args_list[0].kwargs["tools"][0]
            assert "Ukrainian" not in json.dumps(analysis_tool)


class TestTranslation:
    async def test_uk_translates_the_english_result(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("phishing", 0.95, EN_REASONING, ["external domain", "urgency"]),
                    _translation_response(UK_REASONING, ["зовнішній домен", "терміновість"]),
                ]
            )

            result = await classify_email(PARSED, LanguageEnum.UK)

            create = mock_instance.chat.completions.create
            assert _tool_names(create) == ["classify_email", "translate_result"]

            # The translation call is handed the English analysis output.
            sent = json.loads(create.call_args_list[1].kwargs["messages"][1]["content"])
            assert sent == {"reasoning": EN_REASONING, "signals": ["external domain", "urgency"]}

            assert result.reasoning == UK_REASONING
            assert result.signals == ["зовнішній домен", "терміновість"]
            # The verdict comes from the English analysis, untouched by translation.
            assert result.category == EmailCategoryEnum.PHISHING
            assert result.confidence == 0.95
            assert result.reviewed is False

    async def test_english_is_never_translated(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                return_value=_mock_response("spam", 0.95, EN_REASONING, ["a"])
            )

            result = await classify_email(PARSED)

            assert mock_instance.chat.completions.create.call_count == 1
            assert result.reasoning == EN_REASONING

    async def test_failed_translation_falls_back_to_english(self, caplog):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("phishing", 0.95, EN_REASONING, ["external domain"]),
                    RuntimeError("translation api down"),
                ]
            )

            result = await classify_email(PARSED, LanguageEnum.UK)

            assert result.reasoning == EN_REASONING
            assert result.signals == ["external domain"]
            assert result.category == EmailCategoryEnum.PHISHING
            assert "Translation call failed" in caplog.text

    async def test_signal_count_mismatch_falls_back_to_english(self, caplog):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("phishing", 0.95, EN_REASONING, ["one", "two"]),
                    _translation_response(UK_REASONING, ["один"]),
                ]
            )

            result = await classify_email(PARSED, LanguageEnum.UK)

            assert result.reasoning == EN_REASONING
            assert result.signals == ["one", "two"]
            assert "did not match the source shape" in caplog.text

    async def test_empty_result_skips_the_translation_call(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(return_value=_mock_response("spam", 0.95, "", []))

            await classify_email(PARSED, LanguageEnum.UK)

            assert mock_instance.chat.completions.create.call_count == 1

    async def test_translate_result_returns_input_when_nothing_to_translate(self):
        assert await translate_result("", []) == ("", [])


class TestHighRiskCues:
    @pytest.mark.parametrize("cue", HIGH_RISK_CUES)
    def test_every_cue_is_detected_in_the_body(self, cue):
        email = ParsedEmail(sender="a@b.com", to="c@d.com", subject="s", date="d", body=f"text {cue} text")
        assert has_high_risk_cues(email)

    def test_detected_in_the_subject(self):
        email = ParsedEmail(sender="a@b.com", to="c@d.com", subject="Account SUSPENDED", date="d", body="hi")
        assert has_high_risk_cues(email)

    def test_matching_is_case_insensitive(self):
        email = ParsedEmail(sender="a@b.com", to="c@d.com", subject="s", date="d", body="Reset Your PASSWORD")
        assert has_high_risk_cues(email)

    def test_benign_email_has_no_cues(self):
        email = ParsedEmail(
            sender="a@b.com", to="c@d.com", subject="Dinner on Saturday", date="d", body="See you at eight."
        )
        assert not has_high_risk_cues(email)

    async def test_review_runs_on_cues_despite_high_confidence(self):
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(
                side_effect=[
                    _mock_response("transactional", 0.99),
                    _mock_response("phishing", 0.97, "after review"),
                ]
            )

            result = await classify_email(RISKY)

            assert mock_instance.chat.completions.create.call_count == 2
            assert _prompts(mock_instance.chat.completions.create)[1] == REVIEW_PROMPT
            assert result.reviewed is True
            assert result.category == EmailCategoryEnum.PHISHING

    async def test_no_review_for_a_benign_confident_email(self):
        benign = ParsedEmail(
            sender="a@b.com", to="c@d.com", subject="Dinner on Saturday", date="d", body="See you at eight."
        )
        with patch("app.services.classifier.get_client") as mock_get_client:
            mock_instance = mock_get_client.return_value
            mock_instance.chat.completions.create = AsyncMock(return_value=_mock_response("personal", 0.99))

            result = await classify_email(benign)

            assert mock_instance.chat.completions.create.call_count == 1
            assert result.reviewed is False


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
