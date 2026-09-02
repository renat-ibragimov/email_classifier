from app.helpers.enums import LanguageEnum

DEFAULT_LANGUAGE = LanguageEnum.EN

# Telegram interface languages answered in Ukrainian. Russian is on the list on
# purpose: the bot speaks two languages, and Ukrainian is the closer of them for
# a Russian-speaking client.
UKRAINIAN_CLIENT_CODES = frozenset({"uk", "ru"})

# Explicit /lang choices, deliberately in memory: the bot owns no database, and
# a choice is cheap to make again after a restart. Only a chosen language lands
# here — everyone else is read from their Telegram interface language on every
# message, so switching it in Telegram is picked up without asking.
_preferences: dict[int, LanguageEnum] = {}


def detect_language(language_code: str | None) -> LanguageEnum:
    """Read a Telegram interface language as one of the two languages spoken here.

    Args:
        language_code: IETF language tag from the Telegram user, if the client sent one.

    Returns:
        Ukrainian for Ukrainian and Russian clients, DEFAULT_LANGUAGE for everyone
        else and for clients that sent no tag at all.

    """
    if not language_code:
        return DEFAULT_LANGUAGE

    # Clients send anything from "uk" to "en-US" to "pt-br": only the language
    # subtag matters here, and its case is not guaranteed.
    subtag = language_code.split("-")[0].lower()

    return LanguageEnum.UK if subtag in UKRAINIAN_CLIENT_CODES else DEFAULT_LANGUAGE


def resolve_language(user_id: int, language_code: str | None) -> LanguageEnum:
    """Return the language to answer a user in.

    An explicit /lang choice always wins; without one the Telegram interface
    language decides, which is what makes the very first reply land in the right
    language.

    Args:
        user_id: Telegram user id.
        language_code: IETF language tag from the Telegram user, if the client sent one.

    Returns:
        The chosen language, or the one read from the client.

    """
    stored = _preferences.get(user_id)

    return stored if stored is not None else detect_language(language_code)


def stored_language(user_id: int) -> LanguageEnum | None:
    """Return the language a user chose explicitly.

    Args:
        user_id: Telegram user id.

    Returns:
        The stored language, or None if the user never ran /lang.

    """
    return _preferences.get(user_id)


def set_language(user_id: int, language: LanguageEnum) -> None:
    """Store a user's language choice.

    Args:
        user_id: Telegram user id.
        language: Language to store.

    """
    _preferences[user_id] = language


def toggle_language(user_id: int, current: LanguageEnum) -> LanguageEnum:
    """Flip a user between the two supported languages and remember the result.

    Args:
        user_id: Telegram user id.
        current: Language the user is being answered in right now.

    Returns:
        The newly active language.

    """
    updated = LanguageEnum.EN if current is LanguageEnum.UK else LanguageEnum.UK
    set_language(user_id, updated)

    return updated


def reset() -> None:
    """Drop every stored choice. Used to isolate tests."""
    _preferences.clear()
