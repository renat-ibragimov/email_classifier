"""create classification_record table

Revision ID: 001
Revises:
Create Date: 2025-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


status_enum = sa.Enum("pending", "classified", "failed", name="classification_status")
category_enum = sa.Enum(
    "spam", "phishing", "newsletter", "transactional", "personal", "automated",
    name="email_category",
)


def upgrade() -> None:
    op.create_table(
        "classification_record",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, comment="Unique record identifier"),
        sa.Column("content_hash", sa.String(64), unique=True, index=True, nullable=False, comment="SHA-256 hex digest of raw .eml bytes"),
        sa.Column("status", status_enum, nullable=False, server_default="pending", comment="Current state: pending / classified / failed"),
        sa.Column("category", category_enum, nullable=True, comment="Classification result: spam / phishing / newsletter / transactional / personal / automated"),
        sa.Column("confidence", sa.Float, nullable=True, comment="Model confidence score from 0.0 to 1.0"),
        sa.Column("reasoning", sa.Text, nullable=True, comment="LLM explanation of why this category was chosen"),
        sa.Column("signals", ARRAY(sa.String), nullable=True, comment="Specific signals in the email that support the classification"),
        sa.Column("reviewed", sa.Boolean, nullable=False, server_default="false", comment="True if a second LLM pass was performed due to low confidence"),
    )


def downgrade() -> None:
    op.drop_table("classification_record")
    category_enum.drop(op.get_bind())
    status_enum.drop(op.get_bind())
