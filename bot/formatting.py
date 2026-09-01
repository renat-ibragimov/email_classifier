import html

from app.helpers.enums import LanguageEnum
from bot.i18n import category_name, is_flagged, t

MAX_CARD_CHARS = 4000

# Budgets for the two free-text sections, so a very long LLM answer cannot push
# the card past Telegram's message limit. Both are generous for real answers.
REASONING_MAX_CHARS = 1500
SIGNAL_MAX_CHARS = 300
MAX_SIGNALS = 12

ELLIPSIS = "…"


def _truncate(text: str, limit: int) -> str:
    """Cut text to a limit, marking that something was dropped.

    Args:
        text: Text to shorten.
        limit: Maximum length of the result, including the ellipsis.

    Returns:
        The text unchanged, or a shortened version ending in an ellipsis.

    """
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + ELLIPSIS


def _clamp_lines(card: str, limit: int) -> str:
    """Drop whole trailing lines until the card fits.

    Cutting on a line boundary keeps the HTML valid: every tag this module
    emits opens and closes within one line.

    Args:
        card: Rendered card.
        limit: Maximum length.

    Returns:
        The card, shortened to whole lines if it was over the limit.

    """
    if len(card) <= limit:
        return card

    lines = card.split("\n")
    while lines and len("\n".join(lines)) > limit:
        lines.pop()
    return "\n".join(lines)


def _percent(confidence: object) -> str:
    """Render a confidence score as a whole percentage.

    Args:
        confidence: Raw confidence from the API.

    Returns:
        A string like "93%", or an em dash when the value is unusable.

    """
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return "—"
    return f"{round(confidence * 100)}%"


def format_card(payload: dict, language: LanguageEnum, is_duplicate: bool = False) -> str:
    """Render a classification response as an HTML reply card.

    Args:
        payload: Decoded ClassificationResponse body.
        language: Language to render the fixed strings in.
        is_duplicate: True when the API served a cached record.

    Returns:
        HTML string, at most MAX_CARD_CHARS long.

    """
    category = payload.get("category")
    flagged = is_flagged(category)

    verdict = t(language, "verdict_flagged" if flagged else "verdict_clear")
    marker = "\U0001f534" if flagged else "\U0001f7e2"

    lines = [f"{marker} <b>{html.escape(verdict)}</b>", ""]

    category_line = f"<b>{html.escape(t(language, 'category'))}:</b> {html.escape(category_name(language, category))}"
    if payload.get("reviewed"):
        category_line += f" <i>({html.escape(t(language, 'reviewed'))})</i>"
    confidence_line = (
        f"<b>{html.escape(t(language, 'confidence'))}:</b> {html.escape(_percent(payload.get('confidence')))}"
    )
    lines.extend([category_line, confidence_line])

    if is_duplicate:
        lines.append(f"<i>{html.escape(t(language, 'duplicate'))}</i>")

    reasoning = payload.get("reasoning")
    if reasoning:
        lines.extend([
            "",
            f"<b>{html.escape(t(language, 'reasoning'))}</b>",
            html.escape(_truncate(str(reasoning), REASONING_MAX_CHARS)),
        ])

    signals = payload.get("signals") or []
    if signals:
        lines.extend(["", f"<b>{html.escape(t(language, 'signals'))}</b>"])
        for index, signal in enumerate(signals[:MAX_SIGNALS], start=1):
            lines.append(f"{index}. {html.escape(_truncate(str(signal), SIGNAL_MAX_CHARS))}")
        if len(signals) > MAX_SIGNALS:
            lines.append(ELLIPSIS)

    return _clamp_lines("\n".join(lines), MAX_CARD_CHARS)
