from dataclasses import dataclass

from app.helpers.enums import EmailCategoryEnum


@dataclass(frozen=True)
class ParsedEmail:
    """Structured representation of a parsed .eml file."""

    sender: str
    to: str
    subject: str
    date: str
    body: str


@dataclass(frozen=True)
class ClassificationResult:
    """LLM classification output."""

    category: EmailCategoryEnum
    confidence: float
    reasoning: str
    signals: list[str]
    reviewed: bool
