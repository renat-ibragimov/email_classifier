from functools import lru_cache

from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    """Bot settings loaded from environment variables or .env."""

    bot_token: str
    api_base_url: str = "http://email-classifier:8000"
    log_level: str = "INFO"

    # The .env is shared with the API service, so vars the bot does not own
    # (OPENAI_API_KEY, DATABASE_URL, ...) must be ignored rather than rejected.
    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache(maxsize=1)
def get_settings() -> BotSettings:
    """Return the bot settings, built on first use.

    Deferred rather than module-level so importing any bot module does not
    require BOT_TOKEN to be set — the tests rely on that.

    Returns:
        Cached BotSettings.

    """
    return BotSettings()
