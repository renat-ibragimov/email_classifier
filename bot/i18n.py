from app.helpers.enums import EmailCategoryEnum, LanguageEnum

# Categories the bot reports as a threat. The API has no verdict field; this is
# the bot's own reading of the category, matching the web demo.
FLAGGED_CATEGORIES = frozenset({EmailCategoryEnum.PHISHING, EmailCategoryEnum.SPAM})

TEXTS: dict[LanguageEnum, dict[str, str]] = {
    LanguageEnum.EN: {
        "help": (
            "<b>Email Classifier</b>\n"
            "Send me an email and I will tell you whether it looks like phishing, spam, "
            "or something legitimate — and why.\n\n"
            "You can send:\n"
            "• a forwarded message\n"
            "• the text of an email, pasted in\n"
            "• an .eml file (up to 1 MB)\n\n"
            "/lang — switch between Ukrainian and English\n"
            "/help — this message\n\n"
            "<i>Emails are sent to a language model for analysis and are not stored as text.</i>"
        ),
        "language_set": "Language: English.",
        "cmd_help": "What I do and what you can send",
        "cmd_lang": "Switch Ukrainian / English",
        "hint": "Send me an email: forward one, paste its text, or attach an .eml file.",
        "file_too_large": "That file is too large. The limit is 1 MB.",
        "empty_text": "That message has no text to classify.",
        "verdict_flagged": "FLAGGED",
        "verdict_clear": "CLEAR",
        "category": "Category",
        "confidence": "Confidence",
        "reviewed": "second-pass review",
        "reasoning": "Reasoning",
        "signals": "Signals",
        "duplicate": "Already classified earlier — showing the stored result.",
        "error_invalid": "I could not read that as an email. Try forwarding the message or attaching the .eml file.",
        "error_rate_limited": "Too many requests right now. Give it a minute and try again.",
        "error_unavailable": "The classification service is unavailable right now. Please try again later.",
    },
    LanguageEnum.UK: {
        "help": (
            "<b>Класифікатор листів</b>\n"
            "Надішліть мені лист — я скажу, чи схожий він на фішинг, спам, "
            "чи на щось легітимне, і поясню чому.\n\n"
            "Можна надсилати:\n"
            "• переслане повідомлення\n"
            "• текст листа\n"
            "• файл .eml (до 1 МБ)\n\n"
            "/lang — перемкнути українську та англійську\n"
            "/help — це повідомлення\n\n"
            "<i>Листи надсилаються мовній моделі для аналізу і не зберігаються як текст.</i>"
        ),
        "language_set": "Мова: українська.",
        "cmd_help": "Що я вмію і що можна надсилати",
        "cmd_lang": "Перемкнути українську / англійську",
        "hint": "Надішліть мені лист: перешліть повідомлення, вставте текст або прикріпіть файл .eml.",
        "file_too_large": "Цей файл завеликий. Ліміт — 1 МБ.",
        "empty_text": "У цьому повідомленні немає тексту для аналізу.",
        "verdict_flagged": "ЗАГРОЗА",
        "verdict_clear": "ЧИСТО",
        "category": "Категорія",
        "confidence": "Впевненість",
        "reviewed": "повторна перевірка",
        "reasoning": "Обґрунтування",
        "signals": "Ознаки",
        "duplicate": "Цей лист уже перевіряли — показано збережений результат.",
        "error_invalid": "Не вдалося прочитати це як лист. Спробуйте переслати повідомлення або прикріпити файл .eml.",
        "error_rate_limited": "Забагато запитів. Зачекайте хвилину і спробуйте знову.",
        "error_unavailable": "Сервіс класифікації зараз недоступний. Спробуйте пізніше.",
    },
}

# Display names only; the API keeps returning the English enum value.
CATEGORY_NAMES: dict[LanguageEnum, dict[EmailCategoryEnum, str]] = {
    LanguageEnum.EN: {
        EmailCategoryEnum.PHISHING: "phishing",
        EmailCategoryEnum.SPAM: "spam",
        EmailCategoryEnum.NEWSLETTER: "newsletter",
        EmailCategoryEnum.TRANSACTIONAL: "transactional",
        EmailCategoryEnum.PERSONAL: "personal",
        EmailCategoryEnum.AUTOMATED: "automated",
    },
    LanguageEnum.UK: {
        EmailCategoryEnum.PHISHING: "фішинг",
        EmailCategoryEnum.SPAM: "спам",
        EmailCategoryEnum.NEWSLETTER: "розсилка",
        EmailCategoryEnum.TRANSACTIONAL: "транзакційний",
        EmailCategoryEnum.PERSONAL: "особистий",
        EmailCategoryEnum.AUTOMATED: "автоматичний",
    },
}

UNKNOWN_CATEGORY: dict[LanguageEnum, str] = {
    LanguageEnum.EN: "unknown",
    LanguageEnum.UK: "невідомо",
}


def t(language: LanguageEnum, key: str) -> str:
    """Look up a translated string.

    Args:
        language: Language to render in.
        key: Dictionary key.

    Returns:
        The translated string, falling back to English if the key is missing.

    """
    table = TEXTS.get(language, TEXTS[LanguageEnum.EN])
    return table.get(key, TEXTS[LanguageEnum.EN][key])


def category_name(language: LanguageEnum, category: str | None) -> str:
    """Return the display name of a category.

    Args:
        language: Language to render in.
        category: Raw category value from the API, if any.

    Returns:
        The localized category name, or the localized "unknown" placeholder.

    """
    names = CATEGORY_NAMES.get(language, CATEGORY_NAMES[LanguageEnum.EN])
    try:
        return names[EmailCategoryEnum(category)]
    except ValueError:
        return UNKNOWN_CATEGORY.get(language, UNKNOWN_CATEGORY[LanguageEnum.EN])


def is_flagged(category: str | None) -> bool:
    """Read a category as a threat verdict.

    Args:
        category: Raw category value from the API, if any.

    Returns:
        True for phishing and spam, False for everything else.

    """
    try:
        return EmailCategoryEnum(category) in FLAGGED_CATEGORIES
    except ValueError:
        return False
