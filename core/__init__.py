"""
No.1 Trading System - Core Package
Production-grade autonomous multi-asset trading infrastructure.
"""

from core.database import AsyncSessionLocal, init_db, get_engine
from core.events import EventBus
from core.models import (
    Trade,
    Position,
    Order,
    OHLCV,
    StrategyPerformance,
    Signal,
    Alert,
    SystemLog,
    PortfolioSnapshot,
)

__version__ = "1.0.0"
__all__ = [
    "AsyncSessionLocal",
    "init_db",
    "get_engine",
    "EventBus",
    "Trade",
    "Position",
    "Order",
    "OHLCV",
    "StrategyPerformance",
    "Signal",
    "Alert",
    "SystemLog",
    "PortfolioSnapshot",
]
