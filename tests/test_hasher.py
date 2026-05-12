import hashlib

from app.services.hasher import compute_hash


class TestComputeHash:

    def test_returns_sha256_hex_digest(self):
        content = b"test content"
        expected = hashlib.sha256(content).hexdigest()
        assert compute_hash(content) == expected

    def test_digest_length_is_64(self):
        assert len(compute_hash(b"anything")) == 64

    def test_same_content_same_hash(self):
        content = b"duplicate"
        assert compute_hash(content) == compute_hash(content)

    def test_different_content_different_hash(self):
        assert compute_hash(b"one") != compute_hash(b"two")

    def test_empty_content(self):
        assert len(compute_hash(b"")) == 64
