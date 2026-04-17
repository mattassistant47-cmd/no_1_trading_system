"""
Production-grade settings management using Pydantic Settings.
Loads configuration from .env file and environment variables.
"""

from typing import Optional, List, Dict
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    url: str = Field(..., alias="DATABASE_URL")
    pool_size: int = Field(20, alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(40, alias="DATABASE_MAX_OVERFLOW")
    pool_timeout: int = Field(30, alias="DATABASE_POOL_TIMEOUT")
    pool_recycle: int = Field(3600, alias="DATABASE_POOL_RECYCLE")
    echo: bool = False

    class Config:
        env_file = ".env"
        env_prefix = "DATABASE_"


class AlpacaSettings(BaseSettings):
    """Alpaca broker configuration."""

    api_key_paper: str = Field(..., alias="ALPACA_API_KEY_PAPER")
    api_secret_paper: str = Field(..., alias="ALPACA_API_SECRET_PAPER")
    base_url_paper: str = Field("https://paper-api.alpaca.markets", alias="ALPACA_BASE_URL_PAPER")

    api_key_live: str = Field("", alias="ALPACA_API_KEY_LIVE")
    api_secret_live: str = Field("", alias="ALPACA_API_SECRET_LIVE")
    base_url_live: str = Field("https://api.alpaca.markets", alias="ALPACA_BASE_URL_LIVE")

    class Config:
        env_file = ".env"
        env_prefix = "ALPACA_"


class IBKRSettings(BaseSettings):
    """Interactive Brokers configuration."""

    account_id: str = Field("", alias="IBKR_ACCOUNT_ID")
    host: str = Field("127.0.0.1", alias="IBKR_HOST")
    port: int = Field(7497, alias="IBKR_PORT")
    client_id: int = Field(1, alias="IBKR_CLIENT_ID")

    class Config:
        env_file = ".env"
        env_prefix = "IBKR_"


class PolymarketSettings(BaseSettings):
    """Polymarket configuration."""

    api_key: str = Field("", alias="POLYMARKET_API_KEY")
    private_key: str = Field("", alias="POLYMARKET_PRIVATE_KEY")
    base_url: str = Field("https://clob.polymarket.com", alias="POLYMARKET_BASE_URL")

    class Config:
        env_file = ".env"
        env_prefix = "POLYMARKET_"


class FREDSettings(BaseSettings):
    """Federal Reserve Economic Data API configuration."""

    api_key: str = Field(..., alias="FRED_API_KEY")

    class Config:
        env_file = ".env"
        env_prefix = "FRED_"


class TradingSettings(BaseSettings):
    """Core trading parameters and risk limits."""

    initial_capital: float = Field(100000.0, alias="INITIAL_CAPITAL")
    max_position_size_percent: float = Field(0.10, alias="MAX_POSITION_SIZE_PERCENT")
    max_portfolio_risk_percent: float = Field(0.02, alias="MAX_PORTFOLIO_RISK_PERCENT")
    max_leverage: float = Field(2.0, alias="MAX_LEVERAGE")
    min_cash_buffer_percent: float = Field(0.05, alias="MIN_CASH_BUFFER_PERCENT")
    max_slippage_percent: float = Field(0.001, alias="MAX_SLIPPAGE_PERCENT")
    commission_per_trade: float = Field(0.0, alias="COMMISSION_PER_TRADE")
    slippage_percent: float = Field(0.0001, alias="SLIPPAGE_PERCENT")

    # Symbol universes
    equity_symbols: List[str] = Field(
        default_factory=lambda: ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ"],
        alias="EQUITY_SYMBOLS",
    )
    crypto_symbols: List[str] = Field(
        default_factory=lambda: ["BTC/USD", "ETH/USD"],
        alias="CRYPTO_SYMBOLS",
    )

    # Position sizing & timeframe defaults
    default_timeframe: str = Field("1h", alias="DEFAULT_TIMEFRAME")
    default_position_size_pct: float = Field(0.02, alias="DEFAULT_POSITION_SIZE_PCT")
    max_single_position_pct: float = Field(5.0, alias="MAX_SINGLE_POSITION_PCT")
    kelly_fraction: float = Field(0.25, alias="KELLY_FRACTION")
    max_position_size_dollars: float = Field(10000.0, alias="MAX_POSITION_SIZE_DOLLARS")
    min_position_size_dollars: float = Field(1.0, alias="MIN_POSITION_SIZE_DOLLARS")

    # Risk limits
    max_positions: int = Field(30, alias="MAX_POSITIONS")
    max_daily_loss_pct: float = Field(2.0, alias="MAX_DAILY_LOSS_PCT")
    max_drawdown_pct: float = Field(25.0, alias="MAX_DRAWDOWN_PCT")

    # Asset class allocation limits (fraction of portfolio)
    asset_class_limits: Dict[str, float] = Field(
        default_factory=lambda: {
            "EQUITY": 0.50,
            "CRYPTO": 0.20,
            "OPTIONS": 0.20,
            "PREDICTION_MARKET": 0.10,
        }
    )

    @validator("max_position_size_percent", "max_portfolio_risk_percent", "max_leverage")
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    class Config:
        env_file = ".env"


class MomentumStrategySettings(BaseSettings):
    """Momentum strategy parameters."""

    enabled: bool = Field(True, alias="MOMENTUM_ENABLED")
    lookback: int = Field(20, alias="MOMENTUM_LOOKBACK")
    threshold: float = Field(0.05, alias="MOMENTUM_THRESHOLD")
    allocation_weight: float = 0.3

    class Config:
        env_file = ".env"


class MeanReversionStrategySettings(BaseSettings):
    """Mean reversion strategy parameters."""

    enabled: bool = Field(True, alias="MEAN_REVERSION_ENABLED")
    z_score: float = Field(2.0, alias="MEAN_REVERSION_Z_SCORE")
    window: int = Field(30, alias="MEAN_REVERSION_WINDOW")
    allocation_weight: float = 0.3

    class Config:
        env_file = ".env"


class CryptoMomentumStrategySettings(BaseSettings):
    """Crypto momentum strategy - 24/7 trending crypto markets."""

    enabled: bool = Field(True, alias="CRYPTO_MOMENTUM_ENABLED")
    lookback: int = Field(14, alias="CRYPTO_MOMENTUM_LOOKBACK")
    allocation_weight: float = 0.15

    class Config:
        env_file = ".env"


class OptionsWheelStrategySettings(BaseSettings):
    """Options wheel - income from CSP + CC on sideways markets."""

    enabled: bool = Field(True, alias="OPTIONS_WHEEL_ENABLED")
    allocation_weight: float = 0.10
    target_yield_percent: float = 0.05

    class Config:
        env_file = ".env"


class PolymarketStrategySettings(BaseSettings):
    """Polymarket prediction markets - arbitrage and Kelly betting."""

    enabled: bool = Field(True, alias="POLYMARKET_ENABLED")
    allocation_weight: float = 0.05
    confidence_threshold: float = 0.55

    class Config:
        env_file = ".env"


class EnsembleStrategySettings(BaseSettings):
    """Ensemble strategy - aggregates signals from all strategies."""

    enabled: bool = Field(True, alias="ENSEMBLE_ENABLED")
    allocation_weight: float = 0.0  # meta-strategy, no direct allocation
    min_confidence: float = Field(0.6, alias="ENSEMBLE_MIN_CONFIDENCE")

    class Config:
        env_file = ".env"


class BreakoutStrategySettings(BaseSettings):
    """Breakout strategy - volatility expansion / range breaks (equities + crypto)."""

    enabled: bool = Field(True, alias="BREAKOUT_ENABLED")
    lookback: int = Field(20, alias="BREAKOUT_LOOKBACK")
    atr_multiplier: float = Field(2.0, alias="BREAKOUT_ATR_MULT")
    volume_confirmation: bool = Field(True, alias="BREAKOUT_VOLUME_CONF")
    allocation_weight: float = 0.10

    class Config:
        env_file = ".env"


class TrendFollowingStrategySettings(BaseSettings):
    """Trend following - long-term SMA crossover (multi-day horizon)."""

    enabled: bool = Field(True, alias="TREND_FOLLOWING_ENABLED")
    fast_sma: int = Field(50, alias="TREND_FAST_SMA")
    slow_sma: int = Field(200, alias="TREND_SLOW_SMA")
    allocation_weight: float = 0.10

    class Config:
        env_file = ".env"


class PairsTradingStrategySettings(BaseSettings):
    """Pairs trading - statistical arbitrage between correlated assets."""

    enabled: bool = Field(True, alias="PAIRS_TRADING_ENABLED")
    z_entry: float = Field(2.0, alias="PAIRS_Z_ENTRY")
    z_exit: float = Field(0.5, alias="PAIRS_Z_EXIT")
    correlation_min: float = Field(0.70, alias="PAIRS_CORRELATION_MIN")
    allocation_weight: float = 0.10

    class Config:
        env_file = ".env"


class VolatilityRegimeStrategySettings(BaseSettings):
    """Volatility regime - adjusts exposure based on VIX level."""

    enabled: bool = Field(True, alias="VOLATILITY_REGIME_ENABLED")
    vix_low: float = Field(15.0, alias="VIX_LOW_THRESHOLD")
    vix_high: float = Field(25.0, alias="VIX_HIGH_THRESHOLD")
    allocation_weight: float = 0.05

    class Config:
        env_file = ".env"


class SchedulerSettings(BaseSettings):
    """APScheduler configuration."""

    timezone: str = Field("UTC", alias="SCHEDULER_TIMEZONE")
    market_open_hour: int = Field(9, alias="MARKET_OPEN_HOUR")
    market_open_minute: int = Field(30, alias="MARKET_OPEN_MINUTE")
    market_close_hour: int = Field(16, alias="MARKET_CLOSE_HOUR")
    market_close_minute: int = Field(0, alias="MARKET_CLOSE_MINUTE")
    strategy_check_interval_seconds: int = Field(120, alias="STRATEGY_CHECK_INTERVAL_SECONDS")
    risk_check_interval_seconds: int = Field(60, alias="RISK_CHECK_INTERVAL_SECONDS")
    data_sync_interval_seconds: int = Field(60, alias="DATA_SYNC_INTERVAL_SECONDS")
    portfolio_snapshot_interval_minutes: int = Field(1, alias="PORTFOLIO_SNAPSHOT_INTERVAL_MINUTES")
    background_task_initial_delay_seconds: int = Field(5, alias="BACKGROUND_TASK_INITIAL_DELAY")

    class Config:
        env_file = ".env"


class CircuitBreakerSettings(BaseSettings):
    """Circuit breaker risk control configuration."""

    volatility_threshold_sigma: float = Field(3.0, alias="CIRCUIT_BREAKER_VOLATILITY_SIGMA")
    heartbeat_timeout_seconds: int = Field(300, alias="CIRCUIT_BREAKER_HEARTBEAT_TIMEOUT")
    cooldown_minutes: int = Field(60, alias="CIRCUIT_BREAKER_COOLDOWN_MINUTES")
    volatility_min_samples: int = Field(20, alias="CIRCUIT_BREAKER_VOL_MIN_SAMPLES")
    position_size_multipliers: Dict[str, float] = Field(
        default_factory=lambda: {
            "normal": 1.0,
            "warning": 0.75,
            "reduced": 0.5,
            "halted": 0.0,
            "liquidating": 0.0,
        }
    )

    class Config:
        env_file = ".env"


class SecuritySettings(BaseSettings):
    """Security and authentication settings."""

    jwt_secret_key: str = Field("your-secret-key-change-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(24, alias="JWT_EXPIRATION_HOURS")

    class Config:
        env_file = ".env"


class APISettings(BaseSettings):
    """API server configuration."""

    host: str = Field("0.0.0.0", alias="API_HOST")
    port: int = Field(8000, alias="API_PORT")
    workers: int = Field(4, alias="API_WORKERS")
    prometheus_port: int = Field(9090, alias="PROMETHEUS_PORT")

    class Config:
        env_file = ".env"


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: str = Field("INFO", alias="LOG_LEVEL")
    log_file_path: str = Field("/var/log/trading_system.log", alias="LOG_FILE_PATH")
    max_log_size_mb: int = Field(100, alias="MAX_LOG_SIZE_MB")
    log_retention_days: int = Field(30, alias="LOG_RETENTION_DAYS")

    class Config:
        env_file = ".env"


class FeatureFlags(BaseSettings):
    """Feature toggles for system capabilities."""

    enable_backtesting: bool = Field(True, alias="ENABLE_BACKTESTING")
    enable_paper_trading: bool = Field(True, alias="ENABLE_PAPER_TRADING")
    enable_live_trading: bool = Field(False, alias="ENABLE_LIVE_TRADING")
    enable_risk_checks: bool = Field(True, alias="ENABLE_RISK_CHECKS")
    enable_position_sizing: bool = Field(True, alias="ENABLE_POSITION_SIZING")
    enable_performance_tracking: bool = Field(True, alias="ENABLE_PERFORMANCE_TRACKING")

    class Config:
        env_file = ".env"


class Settings(BaseSettings):
    """Main application settings aggregating all sub-configurations."""

    # Application metadata
    mode: str = Field("paper", alias="MODE")
    app_name: str = Field("No.1 Trading System", alias="APP_NAME")
    environment: str = Field("development", alias="ENVIRONMENT")
    debug: bool = Field(False, alias="DEBUG")

    # Sub-configurations
    database: DatabaseSettings = DatabaseSettings()
    alpaca: AlpacaSettings = AlpacaSettings()
    ibkr: IBKRSettings = IBKRSettings()
    polymarket: PolymarketSettings = PolymarketSettings()
    fred: FREDSettings = FREDSettings()

    # Trading parameters
    trading: TradingSettings = TradingSettings()

    # Strategies (10 total — wider regime + asset coverage)
    momentum: MomentumStrategySettings = MomentumStrategySettings()
    mean_reversion: MeanReversionStrategySettings = MeanReversionStrategySettings()
    crypto_momentum: CryptoMomentumStrategySettings = CryptoMomentumStrategySettings()
    options_wheel: OptionsWheelStrategySettings = OptionsWheelStrategySettings()
    polymarket_strategy: PolymarketStrategySettings = PolymarketStrategySettings()
    ensemble: EnsembleStrategySettings = EnsembleStrategySettings()
    breakout: BreakoutStrategySettings = BreakoutStrategySettings()
    trend_following: TrendFollowingStrategySettings = TrendFollowingStrategySettings()
    pairs_trading: PairsTradingStrategySettings = PairsTradingStrategySettings()
    volatility_regime: VolatilityRegimeStrategySettings = VolatilityRegimeStrategySettings()

    # System settings
    scheduler: SchedulerSettings = SchedulerSettings()
    circuit_breaker: CircuitBreakerSettings = CircuitBreakerSettings()
    security: SecuritySettings = SecuritySettings()
    api: APISettings = APISettings()
    logging: LoggingSettings = LoggingSettings()
    features: FeatureFlags = FeatureFlags()

    @validator("mode")
    def validate_mode(cls, v):
        if v not in ("paper", "live"):
            raise ValueError("MODE must be 'paper' or 'live'")
        return v

    @validator("environment")
    def validate_environment(cls, v):
        if v not in ("development", "staging", "production"):
            raise ValueError("ENVIRONMENT must be development, staging, or production")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_alpaca_credentials(self) -> tuple[str, str, str]:
        """Get Alpaca credentials based on current mode.

        Returns:
            Tuple of (api_key, api_secret, base_url)
        """
        if self.mode == "live":
            return (
                self.alpaca.api_key_live,
                self.alpaca.api_secret_live,
                self.alpaca.base_url_live,
            )
        return (
            self.alpaca.api_key_paper,
            self.alpaca.api_secret_paper,
            self.alpaca.base_url_paper,
        )

    def is_live_trading(self) -> bool:
        """Check if live trading is enabled."""
        return self.mode == "live" and self.features.enable_live_trading

    def get_enabled_strategies(self) -> dict[str, bool]:
        """Get dict of enabled strategies across all asset classes + regimes."""
        return {
            # Equities — trending
            "momentum": self.momentum.enabled,
            "trend_following": self.trend_following.enabled,
            "breakout": self.breakout.enabled,
            # Equities — mean-reverting / market-neutral
            "mean_reversion": self.mean_reversion.enabled,
            "pairs_trading": self.pairs_trading.enabled,
            # Crypto
            "crypto_momentum": self.crypto_momentum.enabled,
            # Options (income / sideways)
            "options_wheel": self.options_wheel.enabled,
            # Prediction markets
            "polymarket": self.polymarket_strategy.enabled,
            # Regime / meta strategies
            "volatility_regime": self.volatility_regime.enabled,
            "ensemble": self.ensemble.enabled,
        }


# Global settings instance
settings = Settings()
