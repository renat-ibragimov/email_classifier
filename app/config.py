from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/email_classifier"
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    confidence_threshold: float = 0.85

    model_config = {"env_file": ".env"}


settings = Settings()
