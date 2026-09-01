import hashlib

from app.helpers.enums import LanguageEnum
from app.services.hasher import compute_hash


def _expected(content, language="en"):
    return hashlib.sha256(content + b"\x00" + language.encode()).hexdigest()


class TestComputeHash:
    def test_returns_sha256_hex_digest(self):
        content = b"test content"
        assert compute_hash(content) == _expected(content)

    def test_digest_length_is_64(self):
        assert len(compute_hash(b"anything")) == 64

    def test_same_content_same_hash(self):
        content = b"duplicate"
        assert compute_hash(content) == compute_hash(content)

    def test_different_content_different_hash(self):
        assert compute_hash(b"one") != compute_hash(b"two")

    def test_empty_content(self):
        assert len(compute_hash(b"")) == 64

    def test_language_defaults_to_en(self):
        content = b"same bytes"
        assert compute_hash(content) == compute_hash(content, LanguageEnum.EN)

    def test_different_language_different_hash(self):
        content = b"same bytes"
        assert compute_hash(content, LanguageEnum.EN) != compute_hash(content, LanguageEnum.UK)

    def test_uk_digest_is_stable(self):
        content = b"same bytes"
        assert compute_hash(content, LanguageEnum.UK) == _expected(content, "uk")
