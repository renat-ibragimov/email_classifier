import pytest

from app.helpers.enums import LanguageEnum
from bot import language
from bot.language import DEFAULT_LANGUAGE, get_language, set_language, toggle_language


@pytest.fixture(autouse=True)
def clean_preferences():
    """Keep the in-memory preference store from leaking between tests."""
    language.reset()
    yield
    language.reset()


class TestDefault:
    def test_default_is_ukrainian(self):
        assert DEFAULT_LANGUAGE is LanguageEnum.UK

    def test_unknown_user_gets_the_default(self):
        assert get_language(12345) is LanguageEnum.UK

    def test_users_are_independent(self):
        set_language(1, LanguageEnum.EN)

        assert get_language(1) is LanguageEnum.EN
        assert get_language(2) is LanguageEnum.UK


class TestToggle:
    def test_first_toggle_switches_to_english(self):
        assert toggle_language(1) is LanguageEnum.EN

    def test_toggling_twice_returns_to_ukrainian(self):
        toggle_language(1)

        assert toggle_language(1) is LanguageEnum.UK

    def test_toggle_is_persisted(self):
        toggle_language(1)

        assert get_language(1) is LanguageEnum.EN

    def test_toggle_only_moves_between_the_two_supported_languages(self):
        seen = {toggle_language(1) for _ in range(6)}

        assert seen == {LanguageEnum.EN, LanguageEnum.UK}

    def test_toggle_does_not_affect_other_users(self):
        toggle_language(1)

        assert get_language(2) is LanguageEnum.UK


class TestSet:
    def test_set_overrides_the_default(self):
        set_language(1, LanguageEnum.EN)

        assert get_language(1) is LanguageEnum.EN

    def test_reset_clears_everything(self):
        set_language(1, LanguageEnum.EN)
        language.reset()

        assert get_language(1) is LanguageEnum.UK
