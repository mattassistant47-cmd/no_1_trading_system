"""
Data feed module for multi-asset trading system.

Provides unified access to market data from multiple sources:
- Alpaca (stocks, crypto)
- CoinGecko (additional crypto data)
- FRED (economic indicators)

Includes caching, rate limiting, and error handling.
"""

from data.feeds import DataFeedManager

__all__ = ["DataFeedManager"]

__version__ = "1.0.0"
