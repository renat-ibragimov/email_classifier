import pytest

from bot.config import BotSettings, get_settings


@pytest.fixture(autouse=True)
def clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestBotSettings:
    def test_defaults(self):
        settings = BotSettings(bot_token="token", _env_file=None)

        assert settings.api_base_url == "http://email-classifier:8000"
        assert settings.log_level == "INFO"

    def test_token_is_required(self):
        with pytest.raises(ValueError, match="bot_token"):
            BotSettings(_env_file=None)

    def test_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "from-env")
        monkeypatch.setenv("API_BASE_URL", "https://emails.example.com")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        settings = BotSettings(_env_file=None)

        assert settings.bot_token == "from-env"
        assert settings.api_base_url == "https://emails.example.com"
        assert settings.log_level == "DEBUG"

    def test_ignores_vars_owned_by_the_api_service(self, monkeypatch, tmp_path):
        # The bot shares one .env with the API; its vars must not be rejected.
        env_file = tmp_path / ".env"
        env_file.write_text("BOT_TOKEN=shared\nOPENAI_API_KEY=sk-test\nDATABASE_URL=postgresql://x\n")

        settings = BotSettings(_env_file=str(env_file))

        assert settings.bot_token == "shared"


class TestGetSettings:
    def test_is_built_once(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "cached")

        assert get_settings() is get_settings()
