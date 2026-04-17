"""
Async SQLAlchemy database engine and session setup with connection pooling.
Includes initialization for TimescaleDB hypertables.
"""

import asyncio
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from config.settings import settings
from core.models import Base
from loguru import logger


class DatabaseManager:
    """Manages database connections and initialization."""

    _engine: AsyncEngine | None = None
    _async_session_local: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    async def init(cls) -> None:
        """Initialize the database engine and session maker."""
        logger.info(f"Initializing database with URL: {settings.database.url}")

        cls._engine = create_async_engine(
            settings.database.url,
            echo=settings.database.echo,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_timeout=settings.database.pool_timeout,
            pool_recycle=settings.database.pool_recycle,
            pool_pre_ping=True,
        )

        cls._async_session_local = async_sessionmaker(
            cls._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info("Database engine initialized successfully")

    @classmethod
    async def get_engine(cls) -> AsyncEngine:
        """Get the async engine instance."""
        if cls._engine is None:
            await cls.init()
        return cls._engine

    @classmethod
    async def get_session(cls) -> AsyncSession:
        """Get a new async session."""
        if cls._async_session_local is None:
            await cls.init()
        return cls._async_session_local()

    @classmethod
    async def init_db(cls) -> None:
        """Create all tables and initialize TimescaleDB hypertables."""
        engine = await cls.get_engine()

        # Create tables in one transaction
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created successfully")

        # Migrations in a SEPARATE transaction so they commit even if
        # the TimescaleDB hypertable creation below aborts its transaction.
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS trading_mode VARCHAR(10) DEFAULT 'paper'"
                ))
                await conn.execute(text(
                    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS trading_mode VARCHAR(10) DEFAULT 'paper'"
                ))
                await conn.execute(text(
                    "UPDATE orders SET trading_mode='paper' WHERE trading_mode IS NULL"
                ))
                await conn.execute(text(
                    "UPDATE trades SET trading_mode='paper' WHERE trading_mode IS NULL"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_orders_tmode_filled ON orders(trading_mode, filled_at)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_trades_tmode ON trades(trading_mode)"
                ))
            logger.info("Migrations complete: trading_mode column committed on orders/trades")
        except Exception as e:
            logger.warning(f"Migration step failed: {e}")

        # TimescaleDB extension + hypertables in another separate transaction
        async with engine.begin() as conn:
            # Create TimescaleDB extension if not exists
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
                logger.info("TimescaleDB extension enabled")
            except Exception as e:
                logger.warning(f"TimescaleDB extension already exists or not available: {e}")

            # Convert OHLCV table to hypertable
            try:
                await conn.execute(
                    text(
                        """
                        SELECT create_hypertable(
                            'ohlcv',
                            'timestamp',
                            if_not_exists => TRUE,
                            time_partitioning_func => 'date_trunc(''1 day'', %I)',
                            partitioning_column => 'timestamp'
                        )
                        """
                    )
                )
                logger.info("OHLCV hypertable created")
            except Exception as e:
                logger.warning(f"OHLCV hypertable creation: {e}")

            # Create indexes on hypertable
            try:
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_timestamp ON ohlcv "
                        "(symbol, timestamp DESC)"
                    )
                )
                logger.info("OHLCV indexes created")
            except Exception as e:
                logger.debug(f"OHLCV index creation: {e}")

    @classmethod
    async def close(cls) -> None:
        """Close the database connection."""
        if cls._engine:
            await cls._engine.dispose()
            logger.info("Database connection closed")

    @classmethod
    async def health_check(cls) -> bool:
        """Check database health."""
        try:
            engine = await cls.get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Convenience functions for backward compatibility
async def get_engine() -> AsyncEngine:
    """Get the async database engine."""
    return await DatabaseManager.get_engine()


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    return await DatabaseManager.get_session()


async def init_db() -> None:
    """Initialize the database."""
    await DatabaseManager.init_db()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get async sessions."""
    async with DatabaseManager._async_session_local() as session:
        try:
            yield session
        finally:
            await session.close()


# Global session maker for direct use
AsyncSessionLocal = None


async def setup_database() -> None:
    """Setup database for application startup."""
    global AsyncSessionLocal

    await DatabaseManager.init()
    await DatabaseManager.init_db()
    AsyncSessionLocal = DatabaseManager._async_session_local

    logger.info("Database setup complete")


async def teardown_database() -> None:
    """Cleanup database on application shutdown."""
    await DatabaseManager.close()
    logger.info("Database teardown complete")
