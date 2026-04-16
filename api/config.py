"""
API configuration and settings.
"""

import logging
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class APISettings(BaseSettings):
    """API configuration."""

    # App
    app_name: str = "No.1 Trading System API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    workers: int = 4
    log_level: str = "info"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Security
    api_key_header: str = "x-api-key"
    require_api_key: bool = False
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/trading_system"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_echo: bool = False

    # Trading Engine
    trading_mode: str = "paper"  # paper or live
    engine_timeout: int = 30
    position_update_interval: int = 5  # seconds

    # Brokers
    alpaca_enabled: bool = True
    ibkr_enabled: bool = True
    polymarket_enabled: bool = True

    # Features
    enable_backtesting: bool = True
    enable_optimization: bool = True
    enable_live_trading: bool = False

    # Risk Management
    max_daily_loss: float = 5000.0
    max_position_size: float = 100000.0
    max_leverage: float = 3.0
    max_drawdown: float = 25.0

    # Monitoring
    prometheus_enabled: bool = True
    metrics_port: int = 9090

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> APISettings:
    """Get API settings singleton."""
    return APISettings()


def log_settings():
    """Log current settings (without sensitive data)."""
    settings = get_settings()

    logger.info(f"App: {settings.app_name} v{settings.app_version}")
    logger.info(f"Mode: {'DEBUG' if settings.debug else 'PRODUCTION'}")
    logger.info(f"Server: {settings.host}:{settings.port}")
    logger.info(f"Trading Mode: {settings.trading_mode}")
    logger.info(f"Brokers: Alpaca={settings.alpaca_enabled}, "
                f"IBKR={settings.ibkr_enabled}, Polymarket={settings.polymarket_enabled}")
    logger.info(f"Database: {settings.database_url.split('@')[0]}@{settings.database_url.split('@')[1]}")
    logger.info(f"Risk Limits: Daily Loss=${settings.max_daily_loss}, "
                f"Max Leverage={settings.max_leverage}x, Max Drawdown={settings.max_drawdown}%")
