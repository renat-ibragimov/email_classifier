from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr

from aiogram.types import Message

PLACEHOLDER_ADDRESS = "unknown@example.com"
NO_SUBJECT = "(no subject)"
SUBJECT_MAX_CHARS = 80


def _origin_sender_name(message: Message) -> str | None:
    """Read the original sender's name out of Bot API 7.0 forward metadata.

    Args:
        message: Incoming Telegram message.

    Returns:
        A display name, or None when the message carries no forward origin.

    """
    origin = getattr(message, "forward_origin", None)
    if origin is None:
        return None

    user = getattr(origin, "sender_user", None)
    if user is not None:
        return user.full_name

    chat = getattr(origin, "sender_chat", None) or getattr(origin, "chat", None)
    if chat is not None:
        return chat.title or chat.full_name

    # MessageOriginHiddenUser: the forwarder hid their account, only a name is left.
    return getattr(origin, "sender_user_name", None)


def _legacy_sender_name(message: Message) -> str | None:
    """Read the original sender's name out of pre-7.0 forward fields.

    Args:
        message: Incoming Telegram message.

    Returns:
        A display name, or None when neither legacy field is present.

    """
    # aiogram exposes these removed fields as deprecated properties over
    # forward_origin, and they raise on a message without one. getattr's default
    # covers that as well as the field simply being absent.
    user = getattr(message, "forward_from", None)
    if user is not None:
        return user.full_name
    return getattr(message, "forward_sender_name", None)


def sender_from_message(message: Message) -> str | None:
    """Return the original sender's display name for a forwarded message.

    Args:
        message: Incoming Telegram message.

    Returns:
        The sender's name, or None if the message is not a forward.

    """
    return _origin_sender_name(message) or _legacy_sender_name(message)


def subject_from_text(text: str) -> str:
    """Derive a Subject header from the body text.

    Args:
        text: Full message text.

    Returns:
        The first non-empty line, truncated to SUBJECT_MAX_CHARS, or a placeholder.

    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:SUBJECT_MAX_CHARS]
    return NO_SUBJECT


def build_eml(text: str, sender: str | None = None, sent_at: datetime | None = None) -> bytes:
    """Build a minimal RFC-822 message out of plain text.

    The sender's name, when known, becomes the display part of a placeholder
    address: the API only needs a well-formed non-empty From header, and the
    real address is not something Telegram gives us.

    Args:
        text: Full email text; becomes the body.
        sender: Original sender's display name, if known.
        sent_at: When the message was sent; defaults to now.

    Returns:
        The message serialized as UTF-8 .eml bytes.

    """
    message = EmailMessage()
    message["From"] = formataddr((sender, PLACEHOLDER_ADDRESS)) if sender else PLACEHOLDER_ADDRESS
    message["Subject"] = subject_from_text(text)
    message["Date"] = format_datetime(sent_at or datetime.now(UTC))
    message.set_content(text, charset="utf-8")

    return message.as_bytes()


def build_eml_from_message(message: Message) -> bytes:
    """Build .eml bytes from a forwarded or pasted Telegram message.

    Args:
        message: Incoming Telegram message with text or a caption.

    Returns:
        The message serialized as UTF-8 .eml bytes.

    """
    return build_eml(
        text=message.text or message.caption or "",
        sender=sender_from_message(message),
        sent_at=message.date,
    )
