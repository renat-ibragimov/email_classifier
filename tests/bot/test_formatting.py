import pytest

from app.helpers.enums import LanguageEnum
from bot.formatting import MAX_CARD_CHARS, MAX_SIGNALS, format_card

BASE = {
    "id": "3f2a9c10-0000-4000-8000-000000000001",
    "status": "classified",
    "category": "phishing",
    "confidence": 0.93,
    "reasoning": "The link leaves the organisation.",
    "signals": ["external domain", "urgency"],
    "language": "en",
    "reviewed": False,
    "created_at": "2026-09-01T11:25:00+00:00",
    "model": "gpt-4o-mini",
}


def _payload(**overrides):
    return {**BASE, **overrides}


class TestVerdict:
    @pytest.mark.parametrize("category", ["phishing", "spam"])
    def test_threat_categories_are_flagged(self, category):
        card = format_card(_payload(category=category), LanguageEnum.EN)

        assert "FLAGGED" in card
        assert "\U0001f534" in card

    @pytest.mark.parametrize("category", ["newsletter", "transactional", "personal", "automated"])
    def test_other_categories_are_clear(self, category):
        card = format_card(_payload(category=category), LanguageEnum.EN)

        assert "CLEAR" in card
        assert "\U0001f7e2" in card

    def test_unknown_category_is_clear_and_named(self):
        card = format_card(_payload(category=None), LanguageEnum.EN)

        assert "CLEAR" in card
        assert "unknown" in card

    def test_ukrainian_flagged(self):
        card = format_card(_payload(category="spam"), LanguageEnum.UK)

        assert "ЗАГРОЗА" in card
        assert "спам" in card

    def test_ukrainian_clear(self):
        card = format_card(_payload(category="personal"), LanguageEnum.UK)

        assert "ЧИСТО" in card
        assert "особистий" in card


class TestBody:
    def test_confidence_is_a_percentage(self):
        assert "93%" in format_card(_payload(), LanguageEnum.EN)

    def test_missing_confidence_is_a_dash(self):
        assert "—" in format_card(_payload(confidence=None), LanguageEnum.EN)

    def test_signals_are_numbered(self):
        card = format_card(_payload(), LanguageEnum.EN)

        assert "1. external domain" in card
        assert "2. urgency" in card

    def test_review_note_only_when_reviewed(self):
        assert "second-pass review" in format_card(_payload(reviewed=True), LanguageEnum.EN)
        assert "second-pass review" not in format_card(_payload(reviewed=False), LanguageEnum.EN)

    def test_ukrainian_review_note(self):
        assert "повторна перевірка" in format_card(_payload(reviewed=True), LanguageEnum.UK)

    def test_duplicate_line_only_for_a_cached_result(self):
        assert "Already classified earlier" in format_card(_payload(), LanguageEnum.EN, is_duplicate=True)
        assert "Already classified earlier" not in format_card(_payload(), LanguageEnum.EN, is_duplicate=False)

    def test_ukrainian_duplicate_line(self):
        card = format_card(_payload(), LanguageEnum.UK, is_duplicate=True)

        assert "уже перевіряли" in card

    def test_empty_sections_are_omitted(self):
        card = format_card(_payload(reasoning=None, signals=[]), LanguageEnum.EN)

        assert "Reasoning" not in card
        assert "Signals" not in card

    def test_html_in_llm_text_is_escaped(self):
        card = format_card(_payload(reasoning="<script>alert(1)</script>"), LanguageEnum.EN)

        assert "<script>" not in card
        assert "&lt;script&gt;" in card


class TestTruncation:
    def test_long_reasoning_is_cut(self):
        card = format_card(_payload(reasoning="x" * 5000), LanguageEnum.EN)

        assert len(card) <= MAX_CARD_CHARS
        assert "…" in card

    def test_many_long_signals_stay_within_the_limit(self):
        card = format_card(_payload(reasoning="y" * 2000, signals=["z" * 500] * 40), LanguageEnum.EN)

        assert len(card) <= MAX_CARD_CHARS

    def test_signal_list_is_capped(self):
        card = format_card(_payload(signals=[f"signal {i}" for i in range(40)]), LanguageEnum.EN)

        assert f"{MAX_SIGNALS}. signal {MAX_SIGNALS - 1}" in card
        assert f"{MAX_SIGNALS + 1}." not in card

    def test_verdict_survives_truncation(self):
        card = format_card(_payload(reasoning="x" * 9000, signals=["y" * 900] * 30), LanguageEnum.EN)

        assert len(card) <= MAX_CARD_CHARS
        assert "FLAGGED" in card

    def test_short_card_is_untouched(self):
        card = format_card(_payload(), LanguageEnum.EN)

        assert len(card) < 500
        assert card.count("…") == 0
