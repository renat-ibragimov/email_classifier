from enum import StrEnum


class PgStrEnum(StrEnum):
    """Base enum that uses lowercase values for PostgreSQL compatibility."""

    @classmethod
    def pg_values(cls) -> list[str]:
        """Return all member values as a list of strings."""
        return [member.value for member in cls]


class ClassificationStatusEnum(PgStrEnum):
    """Lifecycle states of a classification record."""

    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class EmailCategoryEnum(PgStrEnum):
    """Email category labels produced by the LLM classifier."""

    SPAM = "spam"
    PHISHING = "phishing"
    NEWSLETTER = "newsletter"
    TRANSACTIONAL = "transactional"
    PERSONAL = "personal"
    AUTOMATED = "automated"
