from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/email_classifier"
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    confidence_threshold: float = 0.85

    # The .env is shared with the bot service, so vars this app does not own
    # (BOT_TOKEN, ...) must be ignored rather than rejected.
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
