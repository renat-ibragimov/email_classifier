import pytest

from app.helpers.dto import ClassificationResult, ParsedEmail
from app.helpers.enums import ClassificationStatusEnum, EmailCategoryEnum


class TestPgValues:

    def test_classification_status_values(self):
        assert ClassificationStatusEnum.pg_values() == ["pending", "classified", "failed"]

    def test_email_category_values(self):
        assert EmailCategoryEnum.pg_values() == [
            "spam",
            "phishing",
            "newsletter",
            "transactional",
            "personal",
            "automated",
        ]

    def test_str_enum_member_is_string(self):
        assert ClassificationStatusEnum.PENDING == "pending"
        assert isinstance(ClassificationStatusEnum.PENDING, str)


class TestParsedEmail:

    def test_frozen(self):
        parsed = ParsedEmail(sender="a@b.com", to="c@d.com", subject="s", date="d", body="b")
        with pytest.raises(AttributeError):
            parsed.sender = "x@y.com"


class TestClassificationResult:

    def test_frozen(self):
        result = ClassificationResult(
            category=EmailCategoryEnum.SPAM,
            confidence=0.9,
            reasoning="r",
            signals=["s"],
            reviewed=False,
        )
        with pytest.raises(AttributeError):
            result.confidence = 0.5
