"""
Broker adapter module for autonomous multi-asset trading system.

Exports all broker implementations for stocks, crypto, and derivatives trading.
"""

from brokers.base import BaseBroker
from brokers.alpaca_broker import AlpacaBroker
from brokers.ibkr_broker import IBKRBroker
from brokers.polymarket_broker import PolymarketBroker

__all__ = [
    "BaseBroker",
    "AlpacaBroker",
    "IBKRBroker",
    "PolymarketBroker",
]

__version__ = "1.0.0"
