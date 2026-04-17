"""Tests for pure-numpy/pandas technical indicators in strategies/indicators.py."""
import numpy as np
import pandas as pd
import pytest

from strategies.indicators import rsi, ema, macd, atr, adx, bbands


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_synthetic_ohlcv(n: int = 100, trend: str = "flat", seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    close = np.cumsum(np.random.randn(n) * 0.5) + 100.0
    if trend == "up":
        close = close + np.linspace(0, 20, n)
    elif trend == "down":
        close = close - np.linspace(0, 20, n)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.random.randint(1000, 100000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

class TestRSI:
    def test_returns_series(self):
        df = make_synthetic_ohlcv(50)
        result = rsi(df["close"], length=14)
        assert isinstance(result, pd.Series)

    def test_output_length_matches_input(self):
        df = make_synthetic_ohlcv(50)
        result = rsi(df["close"], length=14)
        assert len(result) == len(df)

    def test_range_0_100(self):
        df = make_synthetic_ohlcv(100)
        result = rsi(df["close"], length=14).dropna()
        assert (result >= 0).all()
        assert (result <= 100).all()

    def test_first_length_values_nan(self):
        df = make_synthetic_ohlcv(50)
        result = rsi(df["close"], length=14)
        assert result.iloc[:14].isna().all()

    def test_trending_up_rsi_high(self):
        # Pure monotonically rising series -> RSI should saturate near 100
        close = pd.Series(np.linspace(100, 200, 60))
        result = rsi(close, length=14).dropna()
        assert result.iloc[-1] > 70

    def test_trending_down_rsi_low(self):
        close = pd.Series(np.linspace(200, 100, 60))
        result = rsi(close, length=14).dropna()
        assert result.iloc[-1] < 30

    def test_constant_prices(self):
        close = pd.Series([100.0] * 50)
        result = rsi(close, length=14)
        # With no gains and no losses RSI becomes NaN (0/0) — acceptable.
        # Just verify the call produces a Series of the right length.
        assert len(result) == 50

    def test_empty_series(self):
        result = rsi(pd.Series([], dtype=float), length=14)
        assert len(result) == 0

    def test_short_series_all_nan(self):
        close = pd.Series([100.0, 101.0, 102.0])
        result = rsi(close, length=14)
        assert result.isna().all()

    @pytest.mark.parametrize("length", [5, 14, 20, 50])
    def test_different_lengths(self, length):
        df = make_synthetic_ohlcv(200)
        result = rsi(df["close"], length=length)
        assert len(result) == len(df)
        assert result.iloc[:length].isna().all()


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class TestEMA:
    def test_returns_series(self):
        df = make_synthetic_ohlcv(50)
        result = ema(df["close"], length=20)
        assert isinstance(result, pd.Series)

    def test_length_matches(self):
        df = make_synthetic_ohlcv(50)
        result = ema(df["close"], length=20)
        assert len(result) == len(df)

    def test_first_value_equals_input(self):
        close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
        result = ema(close, length=3)
        # EMA adjust=False uses first value as seed
        assert result.iloc[0] == pytest.approx(100.0)

    def test_length_one(self):
        close = pd.Series([100.0])
        result = ema(close, length=5)
        assert len(result) == 1
        assert result.iloc[0] == pytest.approx(100.0)

    def test_empty_input(self):
        result = ema(pd.Series([], dtype=float), length=10)
        assert len(result) == 0

    def test_ema_follows_trend(self):
        close = pd.Series(np.linspace(100, 200, 100))
        result = ema(close, length=10)
        assert result.iloc[-1] > result.iloc[0]

    @pytest.mark.parametrize("length", [5, 14, 20, 50])
    def test_different_lengths(self, length):
        df = make_synthetic_ohlcv(200)
        result = ema(df["close"], length=length)
        assert len(result) == 200


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

class TestMACD:
    def test_returns_dataframe(self):
        df = make_synthetic_ohlcv(100)
        result = macd(df["close"])
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = make_synthetic_ohlcv(100)
        result = macd(df["close"])
        assert "MACD_12_26_9" in result.columns
        assert "MACDs_12_26_9" in result.columns
        assert "MACDh_12_26_9" in result.columns

    def test_histogram_is_macd_minus_signal(self):
        df = make_synthetic_ohlcv(100)
        result = macd(df["close"])
        diff = result["MACD_12_26_9"] - result["MACDs_12_26_9"]
        # Values should match closely (up to float precision)
        assert np.allclose(
            diff.dropna().values,
            result["MACDh_12_26_9"].dropna().values,
            atol=1e-9,
        )

    def test_custom_params(self):
        df = make_synthetic_ohlcv(100)
        result = macd(df["close"], fast=5, slow=10, signal=3)
        assert "MACD_5_10_3" in result.columns
        assert "MACDs_5_10_3" in result.columns
        assert "MACDh_5_10_3" in result.columns

    def test_empty_series(self):
        result = macd(pd.Series([], dtype=float))
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_short_series(self):
        close = pd.Series([100.0, 101.0, 102.0])
        result = macd(close)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

class TestATR:
    def test_returns_series(self):
        df = make_synthetic_ohlcv(50)
        result = atr(df["high"], df["low"], df["close"], length=14)
        assert isinstance(result, pd.Series)

    def test_non_negative(self):
        df = make_synthetic_ohlcv(100)
        result = atr(df["high"], df["low"], df["close"], length=14).dropna()
        assert (result >= 0).all()

    def test_first_length_values_nan(self):
        df = make_synthetic_ohlcv(50)
        result = atr(df["high"], df["low"], df["close"], length=14)
        assert result.iloc[:14].isna().all()

    def test_empty_inputs(self):
        s = pd.Series([], dtype=float)
        result = atr(s, s, s, length=14)
        assert len(result) == 0

    @pytest.mark.parametrize("length", [5, 14, 20])
    def test_different_lengths(self, length):
        df = make_synthetic_ohlcv(100)
        result = atr(df["high"], df["low"], df["close"], length=length)
        assert len(result) == len(df)


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------

class TestADX:
    def test_returns_dataframe(self):
        df = make_synthetic_ohlcv(100)
        result = adx(df["high"], df["low"], df["close"], length=14)
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = make_synthetic_ohlcv(100)
        result = adx(df["high"], df["low"], df["close"], length=14)
        assert "ADX_14" in result.columns
        assert "DMP_14" in result.columns
        assert "DMN_14" in result.columns

    def test_adx_in_range(self):
        df = make_synthetic_ohlcv(200)
        result = adx(df["high"], df["low"], df["close"], length=14)
        a = result["ADX_14"].dropna()
        if len(a):
            assert (a >= 0).all()
            # ADX is bounded at 100 in theory
            assert (a <= 100).all()

    def test_custom_length(self):
        df = make_synthetic_ohlcv(100)
        result = adx(df["high"], df["low"], df["close"], length=20)
        assert "ADX_20" in result.columns


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

class TestBBANDS:
    def test_returns_dataframe(self):
        df = make_synthetic_ohlcv(50)
        result = bbands(df["close"])
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns(self):
        df = make_synthetic_ohlcv(50)
        result = bbands(df["close"])
        assert "BBU_20_2.0" in result.columns
        assert "BBM_20_2.0" in result.columns
        assert "BBL_20_2.0" in result.columns

    def test_upper_above_middle_above_lower(self):
        df = make_synthetic_ohlcv(100)
        result = bbands(df["close"]).dropna()
        if len(result):
            assert (result["BBU_20_2.0"] >= result["BBM_20_2.0"]).all()
            assert (result["BBM_20_2.0"] >= result["BBL_20_2.0"]).all()

    def test_constant_series_zero_width(self):
        close = pd.Series([100.0] * 50)
        result = bbands(close, length=20, std=2.0)
        tail = result.iloc[19:]
        # With zero rolling std, upper == middle == lower
        assert np.allclose(tail["BBU_20_2.0"], tail["BBM_20_2.0"])
        assert np.allclose(tail["BBL_20_2.0"], tail["BBM_20_2.0"])

    def test_custom_params(self):
        df = make_synthetic_ohlcv(50)
        result = bbands(df["close"], length=10, std=1.5)
        assert "BBU_10_1.5" in result.columns
        assert "BBM_10_1.5" in result.columns
        assert "BBL_10_1.5" in result.columns

    @pytest.mark.parametrize("length", [10, 20, 50])
    def test_different_lengths(self, length):
        df = make_synthetic_ohlcv(200)
        result = bbands(df["close"], length=length)
        assert len(result) == len(df)
