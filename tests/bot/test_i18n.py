from app.helpers.enums import EmailCategoryEnum, LanguageEnum
from bot.i18n import CATEGORY_NAMES, TEXTS, category_name, is_flagged, t


class TestDictionaries:
    def test_both_languages_have_the_same_keys(self):
        assert set(TEXTS[LanguageEnum.EN]) == set(TEXTS[LanguageEnum.UK])

    def test_every_category_has_a_name_in_both_languages(self):
        for table in CATEGORY_NAMES.values():
            assert set(table) == set(EmailCategoryEnum)

    def test_ukrainian_category_names(self):
        assert [CATEGORY_NAMES[LanguageEnum.UK][c] for c in EmailCategoryEnum] == [
            "спам",
            "фішинг",
            "розсилка",
            "транзакційний",
            "особистий",
            "автоматичний",
        ]

    def test_privacy_note_is_in_the_help_text(self):
        assert "не зберігаються як текст" in TEXTS[LanguageEnum.UK]["help"]
        assert "not stored as text" in TEXTS[LanguageEnum.EN]["help"]


class TestLookup:
    def test_translates_per_language(self):
        assert t(LanguageEnum.EN, "verdict_flagged") == "FLAGGED"
        assert t(LanguageEnum.UK, "verdict_flagged") == "ЗАГРОЗА"

    def test_category_name_is_localized(self):
        assert category_name(LanguageEnum.EN, "phishing") == "phishing"
        assert category_name(LanguageEnum.UK, "phishing") == "фішинг"

    def test_unknown_category_falls_back(self):
        assert category_name(LanguageEnum.EN, "not-a-category") == "unknown"
        assert category_name(LanguageEnum.UK, None) == "невідомо"


class TestFlagging:
    def test_threats_are_flagged(self):
        assert is_flagged("phishing")
        assert is_flagged("spam")

    def test_everything_else_is_not(self):
        for category in ("newsletter", "transactional", "personal", "automated"):
            assert not is_flagged(category)

    def test_unknown_is_not_flagged(self):
        assert not is_flagged(None)
        assert not is_flagged("garbage")
