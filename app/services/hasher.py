import hashlib


def compute_hash(content: bytes) -> str:
    """Compute SHA-256 hex digest of raw bytes.

    Args:
        content: Raw file content.

    Returns:
        64-character hex digest string.

    """
    return hashlib.sha256(content).hexdigest()
