import email
from email.policy import default

from app.helpers.dto import ParsedEmail


def parse_email(content: bytes) -> ParsedEmail:
    """Parse raw .eml bytes into structured email data.

    Args:
        content: Raw .eml file bytes.

    Returns:
        ParsedEmail with extracted header fields and body text.

    Raises:
        ValueError: If the email is missing the From header.
    """
    msg = email.message_from_bytes(content, policy=default)

    sender = msg.get("From", "")
    if not sender:
        raise ValueError("File is not a valid .eml: missing From header")

    return ParsedEmail(
        sender=sender,
        to=msg.get("To", ""),
        subject=msg.get("Subject", ""),
        date=msg.get("Date", ""),
        body=_extract_body(msg),
    )


def _extract_body(msg: email.message.EmailMessage) -> str:
    """Extract plain text body from an email message.

    Handles both single-part and multipart emails.
    Prefers text/plain over text/html.

    Args:
        msg: Parsed email message object.

    Returns:
        Plain text body content, or empty string if none found.
    """
    # Single-part: return content directly if it is text
    if not msg.is_multipart():
        return msg.get_content() if msg.get_content_type() in ("text/plain", "text/html") else ""

    # Multipart: collect all text and HTML parts
    text_parts = []
    html_parts = []
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/plain":
            text_parts.append(part.get_content())
        elif content_type == "text/html":
            html_parts.append(part.get_content())

    # Combine both: plain text is primary, HTML may contain additional signals
    parts = text_parts + html_parts
    return "\n".join(parts)
