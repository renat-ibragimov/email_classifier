from app.helpers.enums import LanguageEnum

DEFAULT_LANGUAGE = LanguageEnum.UK

# Per-user preference, deliberately in memory: the bot owns no database, and a
# language choice is cheap to make again after a restart.
_preferences: dict[int, LanguageEnum] = {}


def get_language(user_id: int) -> LanguageEnum:
    """Return the language chosen by a user.

    Args:
        user_id: Telegram user id.

    Returns:
        The stored language, or DEFAULT_LANGUAGE if the user never chose one.

    """
    return _preferences.get(user_id, DEFAULT_LANGUAGE)


def set_language(user_id: int, language: LanguageEnum) -> None:
    """Store a user's language preference.

    Args:
        user_id: Telegram user id.
        language: Language to store.

    """
    _preferences[user_id] = language


def toggle_language(user_id: int) -> LanguageEnum:
    """Flip a user between the two supported languages.

    Args:
        user_id: Telegram user id.

    Returns:
        The newly active language.

    """
    current = get_language(user_id)
    updated = LanguageEnum.EN if current is LanguageEnum.UK else LanguageEnum.UK
    set_language(user_id, updated)
    return updated


def reset() -> None:
    """Drop every stored preference. Used to isolate tests."""
    _preferences.clear()
