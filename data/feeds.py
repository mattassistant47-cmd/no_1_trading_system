"""
Unified data feed manager for multi-source market data.

Aggregates data from Alpaca, CoinGecko, and FRED with intelligent
caching, rate limiting, and error handling.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import pandas as pd
from loguru import logger

from data.alpaca_feed import AlpacaDataFeed
from data.coingecko_feed import CoinGeckoDataFeed
from data.fred_feed import FREDDataFeed


class DataFeedManager:
    """
    Manages multiple data feeds with unified interface.

    Features:
    - Automatic feed selection based on asset type
    - Multi-level caching with configurable TTL
    - Rate limit management per source
    - Fallback to alternative sources on error
    """

    def __init__(
        self,
        alpaca_api_key: Optional[str] = None,
        alpaca_secret_key: Optional[str] = None,
        coingecko_api_key: Optional[str] = None,
        fred_api_key: Optional[str] = None,
        cache_ttl_seconds: int = 300,
        **config
    ):
        """
        Initialize data feed manager.

        Args:
            alpaca_api_key: Alpaca API key (for stocks/crypto)
            alpaca_secret_key: Alpaca secret key
            coingecko_api_key: CoinGecko API key (optional, enhances free tier)
            fred_api_key: FRED API key (for economic data)
            cache_ttl_seconds: Cache time-to-live in seconds (default: 5 minutes)
            **config: Additional configuration
        """
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, tuple] = {}  # (data, timestamp)
        self._config = config

        # Initialize data feeds
        self.alpaca = AlpacaDataFeed(
            api_key=alpaca_api_key,
            secret_key=alpaca_secret_key,
        ) if alpaca_api_key else None

        self.coingecko = CoinGeckoDataFeed(
            api_key=coingecko_api_key,
        )

        self.fred = FREDDataFeed(
            api_key=fred_api_key,
        ) if fred_api_key else None

        logger.info(
            f"Initialized DataFeedManager: "
            f"alpaca={'enabled' if self.alpaca else 'disabled'}, "
            f"coingecko=enabled, "
            f"fred={'enabled' if self.fred else 'disabled'}, "
            f"cache_ttl={cache_ttl_seconds}s"
        )

    # Caching utilities
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.cache_ttl):
                logger.debug(f"Cache hit: {key}")
                return data
            else:
                del self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        """Store value in cache."""
        self._cache[key] = (value, datetime.utcnow())
        logger.debug(f"Cached: {key}")

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        source: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get OHLCV (candlestick) data.

        Args:
            symbol: Asset symbol (e.g., 'AAPL', 'BTC/USD')
            timeframe: Candlestick timeframe ('1min', '5min', '15min', '1h', '1d')
            source: Data source ('alpaca', 'coingecko', auto-detect if None)
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        # Auto-detect source if not specified
        if not source:
            source = "coingecko" if "/" in symbol else "alpaca"

        # Check cache
        cache_key = f"ohlcv:{symbol}:{timeframe}:{source}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            if source == "alpaca" and self.alpaca:
                data = await self.alpaca.get_bars(symbol, timeframe, start, end)
            elif source == "coingecko":
                data = await self.coingecko.get_ohlcv(symbol, timeframe)
            else:
                raise ValueError(f"Unknown source: {source}")

            self._set_cached(cache_key, data)
            return data

        except Exception as e:
            logger.error(f"Failed to get OHLCV from {source}: {e}")
            # Try fallback source
            if source == "alpaca" and self.coingecko:
                logger.info(f"Falling back to coingecko for {symbol}")
                return await self.get_ohlcv(symbol, timeframe, "coingecko", start, end)
            raise

    async def get_quote(
        self,
        symbol: str,
        source: Optional[str] = None,
    ) -> Dict[str, float]:
        """
        Get current quote (bid, ask, last).

        Args:
            symbol: Asset symbol
            source: Data source (auto-detect if None)

        Returns:
            Dict with keys: bid, ask, last, bid_size, ask_size
        """
        if not source:
            source = "coingecko" if "/" in symbol else "alpaca"

        cache_key = f"quote:{symbol}:{source}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            if source == "alpaca" and self.alpaca:
                quote = await self.alpaca.get_quote(symbol)
            elif source == "coingecko":
                quote = await self.coingecko.get_price(symbol)
            else:
                raise ValueError(f"Unknown source: {source}")

            self._set_cached(cache_key, quote)
            return quote

        except Exception as e:
            logger.error(f"Failed to get quote from {source}: {e}")
            # Try fallback
            if source == "alpaca" and self.coingecko and "/" in symbol:
                return await self.get_quote(symbol, "coingecko")
            raise

    async def get_crypto_price(
        self,
        coin_id: str,
        vs_currency: str = "usd",
    ) -> Dict[str, float]:
        """
        Get cryptocurrency price from CoinGecko.

        Args:
            coin_id: CoinGecko coin ID (e.g., 'bitcoin', 'ethereum')
            vs_currency: Currency to price in (default: 'usd')

        Returns:
            Dict with price info: {currency: price, market_cap: ..., volume_24h: ...}
        """
        cache_key = f"crypto_price:{coin_id}:{vs_currency}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            price = await self.coingecko.get_coin_data(coin_id, vs_currency)
            self._set_cached(cache_key, price)
            return price

        except Exception as e:
            logger.error(f"Failed to get crypto price for {coin_id}: {e}")
            raise

    async def get_economic_indicator(
        self,
        series_id: str,
    ) -> Optional[float]:
        """
        Get latest economic indicator value from FRED.

        Args:
            series_id: FRED series ID (e.g., 'UNRATE', 'CPIAUCSL', 'DGS10')

        Returns:
            Latest value, or None if not available
        """
        if not self.fred:
            logger.error("FRED not initialized")
            return None

        cache_key = f"fred:{series_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            value = await self.fred.get_series(series_id)
            self._set_cached(cache_key, value)
            return value

        except Exception as e:
            logger.error(f"Failed to get economic indicator {series_id}: {e}")
            return None

    async def get_economic_series(
        self,
        series_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.Series:
        """
        Get time series of economic data from FRED.

        Args:
            series_id: FRED series ID
            start: Start date
            end: End date

        Returns:
            Pandas Series with date index
        """
        if not self.fred:
            raise RuntimeError("FRED not initialized")

        try:
            series = await self.fred.get_series_data(series_id, start, end)
            return series

        except Exception as e:
            logger.error(f"Failed to get economic series {series_id}: {e}")
            raise

    def clear_cache(self, pattern: Optional[str] = None) -> None:
        """
        Clear cache.

        Args:
            pattern: Only clear keys matching this pattern (e.g., 'ohlcv:*')
        """
        if not pattern:
            self._cache.clear()
            logger.info("Cleared entire cache")
        else:
            keys_to_delete = [k for k in self._cache.keys() if pattern.replace("*", "") in k]
            for k in keys_to_delete:
                del self._cache[k]
            logger.info(f"Cleared {len(keys_to_delete)} cache entries matching '{pattern}'")

    async def health_check(self) -> Dict[str, bool]:
        """
        Check health of all configured data sources.

        Returns:
            Dict mapping source name to health status
        """
        health = {}

        if self.alpaca:
            try:
                health["alpaca"] = await self.alpaca.health_check()
            except Exception as e:
                logger.warning(f"Alpaca health check failed: {e}")
                health["alpaca"] = False

        try:
            health["coingecko"] = await self.coingecko.health_check()
        except Exception as e:
            logger.warning(f"CoinGecko health check failed: {e}")
            health["coingecko"] = False

        if self.fred:
            try:
                health["fred"] = await self.fred.health_check()
            except Exception as e:
                logger.warning(f"FRED health check failed: {e}")
                health["fred"] = False

        return health


__all__ = ["DataFeedManager"]
