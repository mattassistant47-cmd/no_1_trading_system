"""Tests for DataFeedManager in data/feeds.py.

External HTTP (Alpaca/CoinGecko/FRED) is mocked throughout — no real calls.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from data.feeds import DataFeedManager


@pytest.fixture
def mgr():
    m = DataFeedManager(
        alpaca_api_key="k",
        alpaca_secret_key="s",
        coingecko_api_key=None,
        fred_api_key=None,
        cache_ttl_seconds=300,
    )
    # Replace underlying feeds with mocks
    m.alpaca = MagicMock()
    m.alpaca.get_bars = AsyncMock()
    m.alpaca.get_quote = AsyncMock()
    m.alpaca.health_check = AsyncMock(return_value=True)

    m.coingecko = MagicMock()
    m.coingecko.get_ohlcv = AsyncMock()
    m.coingecko.get_price = AsyncMock()
    m.coingecko.get_coin_data = AsyncMock()
    m.coingecko.health_check = AsyncMock(return_value=True)
    return m


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [2.0, 3.0],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "volume": [100, 200],
        }
    )


class TestRouting:
    async def test_stock_symbol_routes_to_alpaca(self, mgr):
        mgr.alpaca.get_bars.return_value = _sample_df()
        df = await mgr.get_ohlcv("AAPL", timeframe="1h")
        assert mgr.alpaca.get_bars.called
        assert not mgr.coingecko.get_ohlcv.called
        assert isinstance(df, pd.DataFrame)

    async def test_crypto_slash_routes_to_coingecko(self, mgr):
        mgr.coingecko.get_ohlcv.return_value = _sample_df()
        df = await mgr.get_ohlcv("BTC/USD", timeframe="1h")
        assert mgr.coingecko.get_ohlcv.called
        assert not mgr.alpaca.get_bars.called

    async def test_explicit_source_override(self, mgr):
        mgr.coingecko.get_ohlcv.return_value = _sample_df()
        await mgr.get_ohlcv("AAPL", timeframe="1h", source="coingecko")
        assert mgr.coingecko.get_ohlcv.called


class TestCaching:
    async def test_caches_ohlcv(self, mgr):
        mgr.alpaca.get_bars.return_value = _sample_df()
        await mgr.get_ohlcv("AAPL", timeframe="1h")
        await mgr.get_ohlcv("AAPL", timeframe="1h")
        assert mgr.alpaca.get_bars.call_count == 1

    async def test_cache_ttl_expires(self, mgr):
        mgr.cache_ttl = -1  # already expired
        mgr.alpaca.get_bars.return_value = _sample_df()
        await mgr.get_ohlcv("AAPL", timeframe="1h")
        await mgr.get_ohlcv("AAPL", timeframe="1h")
        assert mgr.alpaca.get_bars.call_count == 2

    def test_clear_cache_full(self, mgr):
        mgr._set_cached("k1", "v1")
        mgr._set_cached("k2", "v2")
        mgr.clear_cache()
        assert mgr._cache == {}

    def test_clear_cache_pattern(self, mgr):
        mgr._set_cached("ohlcv:AAPL:1h", "v1")
        mgr._set_cached("quote:AAPL:alpaca", "v2")
        mgr.clear_cache("ohlcv:*")
        assert "ohlcv:AAPL:1h" not in mgr._cache
        assert "quote:AAPL:alpaca" in mgr._cache


class TestFallback:
    async def test_alpaca_failure_falls_back_to_coingecko(self, mgr):
        mgr.alpaca.get_bars.side_effect = RuntimeError("alpaca down")
        mgr.coingecko.get_ohlcv.return_value = _sample_df()
        df = await mgr.get_ohlcv("AAPL", timeframe="1h")
        assert isinstance(df, pd.DataFrame)
        assert mgr.coingecko.get_ohlcv.called


class TestGetQuote:
    async def test_stock_routes_to_alpaca(self, mgr):
        mgr.alpaca.get_quote.return_value = {"bid": 100, "ask": 101}
        q = await mgr.get_quote("AAPL")
        assert q["bid"] == 100
        assert mgr.alpaca.get_quote.called

    async def test_crypto_routes_to_coingecko(self, mgr):
        mgr.coingecko.get_price.return_value = {"bid": 60000, "ask": 60100}
        q = await mgr.get_quote("BTC/USD")
        assert q["bid"] == 60000


class TestGetCryptoPrice:
    async def test_uses_coingecko(self, mgr):
        mgr.coingecko.get_coin_data.return_value = {"usd": 60000}
        p = await mgr.get_crypto_price("bitcoin", vs_currency="usd")
        assert p["usd"] == 60000


class TestInvalidSource:
    async def test_unknown_source_raises(self, mgr):
        with pytest.raises(ValueError):
            await mgr.get_ohlcv("AAPL", timeframe="1h", source="does_not_exist")


class TestHealthCheck:
    async def test_health_check_returns_dict(self, mgr):
        result = await mgr.health_check()
        assert isinstance(result, dict)
        assert "coingecko" in result


class TestEconomicIndicator:
    async def test_no_fred_returns_none(self):
        m = DataFeedManager(
            alpaca_api_key=None,
            alpaca_secret_key=None,
            coingecko_api_key=None,
            fred_api_key=None,
        )
        val = await m.get_economic_indicator("UNRATE")
        assert val is None
