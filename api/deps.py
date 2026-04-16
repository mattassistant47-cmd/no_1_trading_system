"""
Dependency injection for API endpoints.
"""

import logging
from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import core.database as _db
from core.engine import TradingEngine

logger = logging.getLogger(__name__)

# Global engine instance
_engine: Optional[TradingEngine] = None


def set_engine(engine: TradingEngine) -> None:
    """Set the global engine instance."""
    global _engine
    _engine = engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    if _db.AsyncSessionLocal is None:
        raise HTTPException(
            status_code=503,
            detail="Database not initialized"
        )
    async with _db.AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_engine() -> TradingEngine:
    """Get trading engine instance."""
    if _engine is None:
        raise RuntimeError("Trading engine not initialized")
    return _engine


async def get_settings() -> dict:
    """Get application settings."""
    from config.settings import settings as _settings
    return {
        "environment": _settings.environment,
        "mode": _settings.mode,
        "debug": getattr(_settings, "debug", False),
        "trading_mode": _settings.mode,
        "brokers_enabled": ["alpaca"],
        "strategies_enabled": [],
        "database": "postgresql",
    }


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key from header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # TODO: Implement actual API key validation
    # This is a placeholder for authentication logic
    return x_api_key
