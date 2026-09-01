import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.config import settings
from app.helpers.enums import ClassificationStatusEnum, EmailCategoryEnum


class ClassificationResponse(BaseModel):
    """Response schema for classification endpoints."""

    id: uuid.UUID = Field(description="Unique record identifier")
    status: ClassificationStatusEnum = Field(description="Current state: pending / classified / failed")
    category: EmailCategoryEnum | None = Field(description="Classification result")
    confidence: float | None = Field(description="Model confidence score from 0.0 to 1.0")
    reasoning: str | None = Field(description="LLM explanation of why this category was chosen")
    signals: list[str] | None = Field(description="Specific signals that support the classification")
    reviewed: bool = Field(description="True if a second LLM pass was performed due to low confidence")
    created_at: datetime = Field(description="When the record was first stored")
    model: str = Field(
        default_factory=lambda: settings.openai_model,
        description="OpenAI model used for classification",
    )

    model_config = {"from_attributes": True}
