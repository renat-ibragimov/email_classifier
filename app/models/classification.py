import uuid

from sqlalchemy import Boolean, Enum, Float, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.helpers.enums import ClassificationStatusEnum, EmailCategoryEnum


class ClassificationRecord(Base):
    """Persisted classification result for a single uploaded .eml file."""

    __tablename__ = "classification_record"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique record identifier",
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        comment="SHA-256 hex digest of raw .eml bytes",
    )
    status: Mapped[ClassificationStatusEnum] = mapped_column(
        Enum(
            ClassificationStatusEnum,
            name="classification_status",
            create_type=False,
            values_callable=lambda e: e.pg_values(),
        ),
        default=ClassificationStatusEnum.PENDING,
        comment="Current state: pending / classified / failed",
    )
    category: Mapped[EmailCategoryEnum | None] = mapped_column(
        Enum(
            EmailCategoryEnum,
            name="email_category",
            create_type=False,
            values_callable=lambda e: e.pg_values(),
        ),
        nullable=True,
        comment="Classification result: spam / phishing / newsletter / transactional / personal / automated",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Model confidence score from 0.0 to 1.0",
    )
    reasoning: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="LLM explanation of why this category was chosen",
    )
    signals: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="Specific signals in the email that support the classification",
    )
    reviewed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="True if a second LLM pass was performed due to low confidence",
    )
