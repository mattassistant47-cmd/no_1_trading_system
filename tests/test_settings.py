"""Settings configuration tests."""
import pytest


class TestSettings:
    def test_settings_loads(self):
        from config.settings import settings
        assert settings is not None

    def test_mode_from_env(self):
        from config.settings import settings
        assert settings.mode == "paper"

    def test_environment_from_env(self):
        from config.settings import settings
        assert settings.environment == "development"

    def test_has_database_settings(self):
        from config.settings import settings
        assert hasattr(settings, "database")

    def test_has_alpaca_settings(self):
        from config.settings import settings
        assert hasattr(settings, "alpaca")
