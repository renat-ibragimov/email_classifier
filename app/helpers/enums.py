import enum


class PgStrEnum(str, enum.Enum):
    """Base enum that uses lowercase values for PostgreSQL compatibility."""

    @classmethod
    def pg_values(cls):
        return [member.value for member in cls]


class ClassificationStatusEnum(PgStrEnum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class EmailCategoryEnum(PgStrEnum):
    SPAM = "spam"
    PHISHING = "phishing"
    NEWSLETTER = "newsletter"
    TRANSACTIONAL = "transactional"
    PERSONAL = "personal"
    AUTOMATED = "automated"
