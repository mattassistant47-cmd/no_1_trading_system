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


class TestSubSettings:
    def test_has_trading_settings(self):
        from config.settings import settings
        assert hasattr(settings, "trading")
        assert settings.trading.initial_capital > 0

    def test_has_circuit_breaker_settings(self):
        from config.settings import settings
        assert hasattr(settings, "circuit_breaker")

    def test_has_feature_flags(self):
        from config.settings import settings
        assert hasattr(settings, "features")

    def test_has_scheduler_settings(self):
        from config.settings import settings
        assert hasattr(settings, "scheduler")

    def test_has_api_settings(self):
        from config.settings import settings
        assert hasattr(settings, "api")
        assert settings.api.port > 0

    def test_has_logging_settings(self):
        from config.settings import settings
        assert hasattr(settings, "logging")


class TestCredentials:
    def test_get_alpaca_credentials_paper(self):
        from config.settings import settings
        api_key, secret, url = settings.get_alpaca_credentials()
        assert api_key == "test_key"  # from conftest env
        assert secret == "test_secret"
        assert "paper-api" in url

    def test_get_alpaca_credentials_switches_with_mode(self, monkeypatch):
        # Verify live-mode credentials are returned when mode=='live'.
        # Build a Settings instance then mutate the mode and alpaca creds
        # directly rather than passing unknown constructor kwargs (pydantic
        # Settings rejects extra inputs).
        monkeypatch.setenv("ALPACA_API_KEY_LIVE", "live_k")
        monkeypatch.setenv("ALPACA_API_SECRET_LIVE", "live_s")
        from config.settings import Settings
        s = Settings()
        s.mode = "live"
        s.alpaca.api_key_live = "live_k"
        s.alpaca.api_secret_live = "live_s"
        api_key, secret, url = s.get_alpaca_credentials()
        assert api_key == "live_k"
        assert secret == "live_s"


class TestEnabledStrategies:
    def test_returns_dict(self):
        from config.settings import settings
        d = settings.get_enabled_strategies()
        assert isinstance(d, dict)
        assert "momentum" in d
        assert "mean_reversion" in d


class TestLiveTrading:
    def test_is_live_trading_false_in_paper(self):
        from config.settings import settings
        assert settings.is_live_trading() is False


class TestValidation:
    def test_invalid_mode_raises(self):
        from config.settings import Settings
        with pytest.raises(Exception):
            Settings(mode="bogus")

    def test_invalid_environment_raises(self):
        from config.settings import Settings
        with pytest.raises(Exception):
            Settings(environment="testing")  # validator rejects this


class TestAssetClassLimits:
    def test_asset_class_limits_dict(self):
        from config.settings import settings
        limits = settings.trading.asset_class_limits
        assert "EQUITY" in limits
        assert 0 < limits["EQUITY"] <= 1
