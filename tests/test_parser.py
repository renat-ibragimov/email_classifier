import pytest

from app.services.parser import parse_email

VALID_EML = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Test email\r\n"
    b"Date: Mon, 12 May 2025 10:00:00 +0000\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: text/plain; charset="utf-8"\r\n'
    b"\r\n"
    b"Hello, this is a test email body.\r\n"
)

NO_FROM_EML = (
    b"To: recipient@example.com\r\n"
    b"Subject: No sender\r\n"
    b"\r\n"
    b"Body text.\r\n"
)

MINIMAL_EML = (
    b"From: sender@example.com\r\n"
    b"\r\n"
    b"Just a body.\r\n"
)

HTML_EML = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: HTML email\r\n"
    b'Content-Type: text/html; charset="utf-8"\r\n'
    b"\r\n"
    b"<html><body><p>Hello</p></body></html>\r\n"
)


class TestParseEmail:

    def test_parses_all_fields(self):
        result = parse_email(VALID_EML)
        assert result.sender == "sender@example.com"
        assert result.to == "recipient@example.com"
        assert result.subject == "Test email"
        assert "test email body" in result.body.lower()

    def test_raises_on_missing_from(self):
        with pytest.raises(ValueError, match="missing From header"):
            parse_email(NO_FROM_EML)

    def test_raises_on_garbage_input(self):
        with pytest.raises(ValueError, match="missing From header"):
            parse_email(b"this is not an email at all")

    def test_raises_on_empty_content(self):
        with pytest.raises(ValueError, match="missing From header"):
            parse_email(b"")

    def test_minimal_eml_only_from(self):
        result = parse_email(MINIMAL_EML)
        assert result.sender == "sender@example.com"
        assert result.to == ""
        assert result.subject == ""

    def test_html_body_preserved(self):
        result = parse_email(HTML_EML)
        assert "<html>" in result.body or "Hello" in result.body

    def test_frozen_dataclass(self):
        result = parse_email(VALID_EML)
        with pytest.raises(AttributeError):
            result.sender = "other@example.com"
