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

MULTIPART_EML = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Multipart email\r\n"
    b'Content-Type: multipart/alternative; boundary="BOUNDARY"\r\n'
    b"\r\n"
    b"--BOUNDARY\r\n"
    b'Content-Type: text/plain; charset="utf-8"\r\n'
    b"\r\n"
    b"Plain text body.\r\n"
    b"--BOUNDARY\r\n"
    b'Content-Type: text/html; charset="utf-8"\r\n'
    b"\r\n"
    b"<html><body><p>HTML body</p></body></html>\r\n"
    b"--BOUNDARY--\r\n"
)

NON_TEXT_EML = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Binary attachment\r\n"
    b"Content-Type: application/octet-stream\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    b"aGVsbG8K\r\n"
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

    def test_multipart_combines_plain_and_html(self):
        result = parse_email(MULTIPART_EML)
        assert "Plain text body" in result.body
        assert "<html>" in result.body or "HTML body" in result.body
        plain_idx = result.body.find("Plain text body")
        html_idx = result.body.find("HTML body")
        assert plain_idx < html_idx

    def test_non_text_content_returns_empty_body(self):
        result = parse_email(NON_TEXT_EML)
        assert result.sender == "sender@example.com"
        assert result.body == ""
