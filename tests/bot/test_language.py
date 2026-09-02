import pytest

from app.helpers.enums import LanguageEnum
from bot import language
from bot.language import (
    DEFAULT_LANGUAGE,
    detect_language,
    resolve_language,
    set_language,
    stored_language,
    toggle_language,
)


@pytest.fixture(autouse=True)
def clean_preferences():
    """Keep the in-memory preference store from leaking between tests."""
    language.reset()
    yield
    language.reset()


class TestDetection:
    def test_default_is_english(self):
        assert DEFAULT_LANGUAGE is LanguageEnum.EN

    def test_ukrainian_clients_get_ukrainian(self):
        assert detect_language("uk") is LanguageEnum.UK

    def test_russian_clients_get_ukrainian(self):
        assert detect_language("ru") is LanguageEnum.UK

    def test_every_other_language_gets_english(self):
        for code in ("en", "de", "pl", "es", "zh", "ar"):
            assert detect_language(code) is LanguageEnum.EN

    def test_a_missing_code_gets_the_default(self):
        assert detect_language(None) is LanguageEnum.EN
        assert detect_language("") is LanguageEnum.EN

    def test_the_region_subtag_is_ignored(self):
        assert detect_language("uk-UA") is LanguageEnum.UK
        assert detect_language("ru-RU") is LanguageEnum.UK
        assert detect_language("en-US") is LanguageEnum.EN

    def test_case_does_not_matter(self):
        assert detect_language("UK") is LanguageEnum.UK
        assert detect_language("ru-ru") is LanguageEnum.UK

    def test_an_unparseable_code_falls_back_instead_of_raising(self):
        assert detect_language("-") is LanguageEnum.EN
        assert detect_language("nonsense") is LanguageEnum.EN


class TestResolution:
    def test_an_unknown_user_follows_their_client(self):
        assert resolve_language(1, "uk") is LanguageEnum.UK
        assert resolve_language(2, "de") is LanguageEnum.EN

    def test_a_chosen_language_beats_the_client(self):
        set_language(1, LanguageEnum.EN)

        assert resolve_language(1, "uk") is LanguageEnum.EN

    def test_users_are_independent(self):
        set_language(1, LanguageEnum.UK)

        assert resolve_language(1, "en") is LanguageEnum.UK
        assert resolve_language(2, "en") is LanguageEnum.EN

    def test_nothing_is_stored_just_by_resolving(self):
        resolve_language(1, "uk")

        assert stored_language(1) is None


class TestToggle:
    def test_toggling_off_english_gives_ukrainian(self):
        assert toggle_language(1, LanguageEnum.EN) is LanguageEnum.UK

    def test_toggling_off_ukrainian_gives_english(self):
        assert toggle_language(1, LanguageEnum.UK) is LanguageEnum.EN

    def test_the_choice_is_stored(self):
        toggle_language(1, LanguageEnum.EN)

        assert stored_language(1) is LanguageEnum.UK

    def test_a_stored_choice_survives_a_different_client_language(self):
        toggle_language(1, LanguageEnum.EN)

        assert resolve_language(1, "de") is LanguageEnum.UK

    def test_toggling_twice_returns_to_the_start(self):
        toggle_language(1, LanguageEnum.EN)

        assert toggle_language(1, LanguageEnum.UK) is LanguageEnum.EN

    def test_toggle_does_not_affect_other_users(self):
        toggle_language(1, LanguageEnum.EN)

        assert stored_language(2) is None


class TestStore:
    def test_set_overrides_detection(self):
        set_language(1, LanguageEnum.UK)

        assert stored_language(1) is LanguageEnum.UK

    def test_an_unknown_user_has_no_stored_language(self):
        assert stored_language(12345) is None

    def test_reset_clears_everything(self):
        set_language(1, LanguageEnum.UK)
        language.reset()

        assert stored_language(1) is None
