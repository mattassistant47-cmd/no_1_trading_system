"""
CoinGecko data feed for cryptocurrency data.

Provides OHLCV data, prices, market cap, and fundamentals for crypto assets
using the free tier API (5-15 calls/minute) and optional premium access.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd
from loguru import logger
import httpx
import asyncio
from enum import Enum

# Rate limiting
class RateLimiter:
    """Simple async rate limiter."""

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: list = []

    async def wait(self):
        """Wait until next call is allowed."""
        now = asyncio.get_event_loop().time()
        cutoff = now - self.window_seconds

        # Remove old calls
        self.calls = [t for t in self.calls if t > cutoff]

        if len(self.calls) >= self.max_calls:
            sleep_time = self.calls[0] - cutoff + 0.1
            await asyncio.sleep(sleep_time)

        self.calls.append(now)


class CoinGeckoDataFeed:
    """
    CoinGecko data feed for cryptocurrencies.

    Features:
    - Free tier: 5-15 calls/minute (no API key required)
    - Pro tier: Higher rate limits (with API key)
    - Historical OHLCV data
    - Current prices and market data
    - Supports 250+ cryptocurrencies
    """

    BASE_URL = "https://api.coingecko.com/api/v3"
    TIMEFRAME_MAPPING = {
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
        "1w": 604800,
        "30d": 2592000,
    }

    def __init__(self, api_key: Optional[str] = None, **config):
        """
        Initialize CoinGecko data feed.

        Args:
            api_key: Optional CoinGecko Pro API key
            **config: Additional configuration
        """
        self.api_key = api_key
        self.config = config

        # Rate limiter: free tier = 10 calls/min, pro = 50 calls/min
        calls_per_minute = 50 if api_key else 10
        self.rate_limiter = RateLimiter(
            max_calls=calls_per_minute,
            window_seconds=60,
        )

        # HTTP client
        headers = {}
        if api_key:
            headers["x-cg-pro-api-key"] = api_key

        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=30.0,
        )

        logger.info(
            f"Initialized CoinGecko feed: "
            f"tier={'pro' if api_key else 'free'}, "
            f"rate_limit={calls_per_minute}/min"
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        days: int = 30,
    ) -> pd.DataFrame:
        """
        Get OHLCV data for a cryptocurrency pair.

        Args:
            symbol: Crypto pair symbol (e.g., 'BTC/USD', 'bitcoin/usd')
            timeframe: Timeframe ('1h', '4h', '1d', '1w', '30d')
            days: Days of history to retrieve (default: 30)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        try:
            # Parse symbol
            if "/" in symbol:
                coin_id, vs = symbol.lower().split("/")
            else:
                coin_id = symbol.lower()
                vs = "usd"

            # Normalize coin ID
            coin_id = self._normalize_coin_id(coin_id)

            await self.rate_limiter.wait()

            # Request market chart data
            response = await self.client.get(
                f"/coins/{coin_id}/market_chart",
                params={
                    "vs_currency": vs,
                    "days": days,
                    "interval": "daily" if days >= 90 else None,
                },
            )
            response.raise_for_status()

            data = response.json()
            prices = data.get("prices", [])

            if not prices:
                logger.warning(f"No price data for {coin_id}")
                return pd.DataFrame()

            # Convert to OHLCV format
            # CoinGecko provides [timestamp, price] pairs
            # We'll approximate OHLC from daily prices
            df = pd.DataFrame(prices, columns=["timestamp", "close"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df["open"] = df["close"].shift(1)
            df["high"] = df["close"].rolling(window=1).max()
            df["low"] = df["close"].rolling(window=1).min()
            df["volume"] = 0  # CoinGecko doesn't provide volume in market_chart

            df = df.set_index("timestamp")
            df = df[["open", "high", "low", "close", "volume"]]
            df = df.ffill()

            logger.debug(f"Retrieved {len(df)} OHLCV records for {coin_id}")
            return df

        except httpx.HTTPStatusError as e:
            # 429 rate-limit: back off and return empty so callers degrade gracefully
            if e.response.status_code == 429:
                logger.warning(f"CoinGecko rate-limited for {symbol}; backing off 60s")
                await asyncio.sleep(60)
                return pd.DataFrame()
            logger.error(f"Failed to get OHLCV for {symbol}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get OHLCV for {symbol}: {e}")
            return pd.DataFrame()

    async def get_price(
        self,
        symbol: str,
        include_market_cap: bool = True,
        include_24h_vol: bool = True,
    ) -> Dict[str, Any]:
        """
        Get current price and market data.

        Args:
            symbol: Crypto pair (e.g., 'BTC/USD')
            include_market_cap: Include market cap data
            include_24h_vol: Include 24h volume

        Returns:
            Dict with price and optional market data
        """
        try:
            if "/" in symbol:
                coin_id, vs = symbol.lower().split("/")
            else:
                coin_id = symbol.lower()
                vs = "usd"

            coin_id = self._normalize_coin_id(coin_id)

            await self.rate_limiter.wait()

            params = {"ids": coin_id, "vs_currencies": vs}
            if include_market_cap:
                params["include_market_cap"] = "true"
            if include_24h_vol:
                params["include_24hr_vol"] = "true"

            response = await self.client.get(
                "/simple/price",
                params=params,
            )
            response.raise_for_status()

            data = response.json()
            if coin_id not in data:
                logger.warning(f"Coin {coin_id} not found")
                return {}

            coin_data = data[coin_id]
            return {
                "price": coin_data.get(vs),
                "market_cap": coin_data.get(f"{vs}_market_cap"),
                "volume_24h": coin_data.get(f"{vs}_24h_vol"),
            }

        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            raise

    async def get_coin_data(
        self,
        coin_id: str,
        vs_currency: str = "usd",
    ) -> Dict[str, Any]:
        """
        Get comprehensive coin data.

        Args:
            coin_id: CoinGecko coin ID (e.g., 'bitcoin', 'ethereum')
            vs_currency: Currency for pricing

        Returns:
            Dict with market data, price, 24h change, etc.
        """
        try:
            coin_id = self._normalize_coin_id(coin_id)

            await self.rate_limiter.wait()

            response = await self.client.get(
                f"/coins/{coin_id}",
                params={
                    "localization": "false",
                    "sparkline": "false",
            },
            )
            response.raise_for_status()

            data = response.json()
            market_data = data.get("market_data", {})

            return {
                "name": data.get("name"),
                "symbol": data.get("symbol", "").upper(),
                "price": market_data.get("current_price", {}).get(vs_currency.lower()),
                "market_cap": market_data.get("market_cap", {}).get(vs_currency.lower()),
                "market_cap_rank": data.get("market_cap_rank"),
                "volume_24h": market_data.get("total_volume", {}).get(vs_currency.lower()),
                "high_24h": market_data.get("high_24h", {}).get(vs_currency.lower()),
                "low_24h": market_data.get("low_24h", {}).get(vs_currency.lower()),
                "change_24h": market_data.get("price_change_percentage_24h"),
                "circulating_supply": data.get("circulating_supply"),
                "total_supply": data.get("total_supply"),
            }

        except Exception as e:
            logger.error(f"Failed to get coin data for {coin_id}: {e}")
            raise

    async def search_coins(self, query: str) -> list:
        """
        Search for coins by name or symbol.

        Args:
            query: Search query

        Returns:
            List of matching coins with IDs
        """
        try:
            await self.rate_limiter.wait()

            response = await self.client.get(
                "/search",
                params={"query": query},
            )
            response.raise_for_status()

            data = response.json()
            coins = data.get("coins", [])

            return [
                {
                    "id": coin["id"],
                    "name": coin["name"],
                    "symbol": coin["symbol"],
                }
                for coin in coins[:10]  # Return top 10 results
            ]

        except Exception as e:
            logger.error(f"Failed to search coins: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Check if CoinGecko API is accessible.

        Returns:
            True if API is responding
        """
        try:
            await self.rate_limiter.wait()
            response = await self.client.get("/ping")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"CoinGecko health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    def _normalize_coin_id(self, coin_id: str) -> str:
        """
        Normalize coin ID to CoinGecko format.

        Converts common symbols to CoinGecko IDs.
        """
        mapping = {
            "btc": "bitcoin",
            "eth": "ethereum",
            "bnb": "binancecoin",
            "xrp": "ripple",
            "ada": "cardano",
            "sol": "solana",
            "dot": "polkadot",
            "usdt": "tether",
            "usdc": "usd-coin",
            "doge": "dogecoin",
            "matic": "matic-network",
        }

        return mapping.get(coin_id.lower(), coin_id.lower())


__all__ = ["CoinGeckoDataFeed"]
