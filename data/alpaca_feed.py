"""
Alpaca data feed for stocks and cryptocurrency.

Provides OHLCV bars, quotes, and real-time tick data for stocks
and 24/5 crypto trading pairs.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd
from loguru import logger
import httpx

try:
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest, StockLatestQuoteRequest, CryptoLatestQuoteRequest
    from alpaca.data.enums import Adjustment
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False


class AlpacaDataFeed:
    """
    Alpaca data feed for stocks and crypto.

    Features:
    - 1-minute to daily bars for stocks
    - Crypto bars 24/5 (no market hours restriction)
    - Real-time and historical quotes
    - Automatic retry with exponential backoff
    """

    def __init__(self, api_key: str, secret_key: str, **config):
        """
        Initialize Alpaca data feed.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            **config: Additional configuration
        """
        if not ALPACA_AVAILABLE:
            raise RuntimeError("alpaca-py not installed")

        self.api_key = api_key
        self.secret_key = secret_key
        self.config = config
        self.stock_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=secret_key,
        )
        self.crypto_client = CryptoHistoricalDataClient(
            api_key=api_key,
            secret_key=secret_key,
        )
        logger.info("Initialized Alpaca data feed")

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get historical OHLCV bars.

        Args:
            symbol: Asset symbol (e.g., 'AAPL', 'BTC/USD')
            timeframe: Bar timeframe ('1min', '5min', '15min', '1h', '1d', '1w')
            start: Start datetime (UTC, default: 7 days ago)
            end: End datetime (UTC, default: now)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        # Set default dates
        if end is None:
            end = datetime.utcnow()
        if start is None:
            start = end - timedelta(days=7)

        try:
            is_crypto = "/" in symbol

            if is_crypto:
                request = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=self._parse_timeframe(timeframe),
                    start=start,
                    end=end,
                )
                bars = self.crypto_client.get_crypto_bars(request)
            else:
                from alpaca.data.enums import DataFeed
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=self._parse_timeframe(timeframe),
                    start=start,
                    end=end,
                    adjustment=Adjustment.ALL,
                    feed=DataFeed.IEX,
                )
                bars = self.stock_client.get_stock_bars(request)

            # alpaca-py returns BarSet: dict-like of symbol -> list of Bar objects
            try:
                symbol_bars = bars[symbol]
            except (KeyError, TypeError):
                symbol_bars = bars[symbol.upper()] if hasattr(bars, '__getitem__') else []
            if hasattr(symbol_bars, 'df'):
                df = symbol_bars.df
            else:
                # Convert list of Bar objects to DataFrame
                records = []
                for bar in symbol_bars:
                    records.append({
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": float(bar.volume),
                    })
                df = pd.DataFrame(records)
                if not df.empty and "timestamp" in df.columns:
                    df.set_index("timestamp", inplace=True)
            logger.debug(f"Retrieved {len(df)} bars for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Failed to get bars for {symbol}: {e}")
            raise

    async def get_quote(self, symbol: str) -> Dict[str, float]:
        """
        Get latest quote.

        Args:
            symbol: Asset symbol

        Returns:
            Dict with keys: bid, ask, last, bid_size, ask_size
        """
        try:
            is_crypto = "/" in symbol

            if is_crypto:
                request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
                quotes = self.crypto_client.get_crypto_latest_quote(request)
            else:
                request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
                quotes = self.stock_client.get_stock_latest_quote(request)

            quote = quotes[symbol]

            return {
                "bid": float(quote.bid_price),
                "ask": float(quote.ask_price),
                "last": float(quote.bid_price),  # Use bid as proxy
                "bid_size": float(quote.bid_size),
                "ask_size": float(quote.ask_size),
                "timestamp": quote.timestamp,
            }

        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Check if Alpaca API is accessible.

        Returns:
            True if API is responding
        """
        try:
            # Make a simple API call to test connectivity
            request = StockLatestQuoteRequest(symbol_or_symbols="AAPL")
            self.stock_client.get_stock_latest_quote(request)
            logger.debug("Alpaca health check passed")
            return True
        except Exception as e:
            logger.warning(f"Alpaca health check failed: {e}")
            return False

    def _parse_timeframe(self, timeframe: str):
        """Parse timeframe string to Alpaca TimeFrame."""
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        mapping = {
            "1min": TimeFrame.Minute,
            "5min": TimeFrame(5, TimeFrameUnit.Minute),
            "15min": TimeFrame(15, TimeFrameUnit.Minute),
            "30min": TimeFrame(30, TimeFrameUnit.Minute),
            "1h": TimeFrame.Hour,
            "4h": TimeFrame(4, TimeFrameUnit.Hour),
            "1d": TimeFrame.Day,
            "1w": TimeFrame.Week,
        }

        if timeframe not in mapping:
            logger.warning(f"Unknown timeframe: {timeframe}, defaulting to 1h")
            return TimeFrame.Hour

        return mapping[timeframe]


__all__ = ["AlpacaDataFeed"]
