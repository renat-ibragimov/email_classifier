import hashlib

from app.helpers.enums import LanguageEnum


def compute_hash(content: bytes, language: LanguageEnum = LanguageEnum.EN) -> str:
    """Compute SHA-256 hex digest of raw bytes scoped to a language.

    The language is part of the digest so the same file requested in another
    language is a different record instead of a cache hit on the first one.

    Args:
        content: Raw file content.
        language: Language the classification was requested in.

    Returns:
        64-character hex digest string.

    """
    return hashlib.sha256(content + b"\x00" + language.value.encode()).hexdigest()
