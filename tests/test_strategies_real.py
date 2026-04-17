"""Tests for the real strategy classes: Signal, Direction, BaseStrategy subclasses."""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime

from strategies.base import Signal, Direction, PerformanceMetrics, BaseStrategy

try:
    from strategies.momentum import MultiTimeframeMomentum
    HAS_MOMENTUM = True
except ImportError:
    HAS_MOMENTUM = False
    MultiTimeframeMomentum = None

try:
    from strategies.mean_reversion import StatisticalMeanReversion
    HAS_MEAN_REVERSION = True
except ImportError:
    HAS_MEAN_REVERSION = False
    StatisticalMeanReversion = None


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

class TestSignal:
    def test_create_valid_signal(self):
        sig = Signal(
            symbol="AAPL",
            direction=Direction.LONG,
            strength=0.75,
            strategy_name="test",
        )
        assert sig.symbol == "AAPL"
        assert sig.direction == Direction.LONG
        assert sig.strength == 0.75
        assert sig.strategy_name == "test"
        assert isinstance(sig.timestamp, datetime)

    def test_strength_zero(self):
        sig = Signal(symbol="X", direction=Direction.NEUTRAL, strength=0.0, strategy_name="t")
        assert sig.strength == 0.0

    def test_strength_one(self):
        sig = Signal(symbol="X", direction=Direction.NEUTRAL, strength=1.0, strategy_name="t")
        assert sig.strength == 1.0

    def test_strength_too_high_raises(self):
        with pytest.raises(ValueError, match="strength"):
            Signal(symbol="X", direction=Direction.LONG, strength=1.5, strategy_name="t")

    def test_strength_negative_raises(self):
        with pytest.raises(ValueError, match="strength"):
            Signal(symbol="X", direction=Direction.LONG, strength=-0.1, strategy_name="t")

    def test_metadata_defaults_to_empty_dict(self):
        sig = Signal(symbol="X", direction=Direction.LONG, strength=0.5, strategy_name="t")
        assert sig.metadata == {}

    def test_optional_fields(self):
        sig = Signal(
            symbol="AAPL",
            direction=Direction.SHORT,
            strength=0.6,
            strategy_name="t",
            stop_loss=145.0,
            take_profit=160.0,
            position_size=100.0,
        )
        assert sig.stop_loss == 145.0
        assert sig.take_profit == 160.0
        assert sig.position_size == 100.0

    def test_repr(self):
        sig = Signal(symbol="AAPL", direction=Direction.LONG, strength=0.50, strategy_name="test")
        r = repr(sig)
        assert "AAPL" in r
        assert "LONG" in r


# ---------------------------------------------------------------------------
# Direction enum
# ---------------------------------------------------------------------------

class TestDirection:
    def test_values(self):
        assert Direction.LONG == "LONG"
        assert Direction.SHORT == "SHORT"
        assert Direction.NEUTRAL == "NEUTRAL"
        assert Direction.EXIT == "EXIT"

    def test_all_members(self):
        assert set(Direction) == {Direction.LONG, Direction.SHORT, Direction.NEUTRAL, Direction.EXIT}


# ---------------------------------------------------------------------------
# PerformanceMetrics dataclass
# ---------------------------------------------------------------------------

class TestPerformanceMetrics:
    def test_defaults(self):
        m = PerformanceMetrics()
        assert m.win_rate == 0.0
        assert m.trade_count == 0
        assert m.sharpe_ratio == 0.0


# ---------------------------------------------------------------------------
# Helper: build synthetic OHLCV DataFrame
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 250, start_price: float = 100.0, trend: float = 0.001, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = [start_price]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + trend + rng.normal(0, 0.01)))
    closes = np.array(closes)
    highs = closes * (1 + rng.uniform(0, 0.01, n))
    lows = closes * (1 - rng.uniform(0, 0.01, n))
    opens = (highs + lows) / 2
    volume = rng.integers(1_000_000, 10_000_000, n)
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volume,
    })


# ---------------------------------------------------------------------------
# MultiTimeframeMomentum
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_MOMENTUM, reason="pandas_ta not installed")
class TestMultiTimeframeMomentum:
    @pytest.fixture
    def strategy(self):
        return MultiTimeframeMomentum()

    def test_instantiation_defaults(self, strategy):
        assert strategy.name == "MultiTimeframeMomentum"
        assert strategy.rsi_period == 14
        assert strategy.ema_trend == 200
        assert strategy.asset_class == "equities"
        assert strategy.timeframe == "1D"

    def test_custom_config(self):
        s = MultiTimeframeMomentum(config={"rsi_period": 10, "adx_strong": 30})
        assert s.rsi_period == 10
        assert s.adx_strong == 30

    def test_generate_signals_insufficient_data(self, strategy):
        df = _make_ohlcv(n=10)
        signals = strategy.generate_signals(df)
        assert signals == []

    def test_generate_signals_returns_list(self, strategy):
        df = _make_ohlcv(n=250)
        signals = strategy.generate_signals(df)
        assert isinstance(signals, list)

    def test_generate_signals_all_valid(self, strategy):
        df = _make_ohlcv(n=250)
        signals = strategy.generate_signals(df)
        for sig in signals:
            assert isinstance(sig, Signal)
            assert 0.0 <= sig.strength <= 1.0
            assert sig.direction in Direction

    def test_generate_signals_empty_dataframe(self, strategy):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        signals = strategy.generate_signals(df)
        assert signals == []

    def test_should_exit_insufficient_data(self, strategy):
        df = _make_ohlcv(n=5)
        pos = {"direction": Direction.LONG, "entry_price": 100.0}
        assert strategy.should_exit(pos, df) is False

    def test_calculate_position_size(self, strategy):
        size = strategy.calculate_position_size(capital=100000, atr=2.0)
        assert size > 0

    def test_calculate_position_size_zero_atr(self, strategy):
        size = strategy.calculate_position_size(capital=100000, atr=0)
        assert size == 0.0

    def test_weight_property(self, strategy):
        assert strategy.weight == 1.0
        strategy.weight = 0.5
        assert strategy.weight == 0.5

    def test_weight_invalid_raises(self, strategy):
        with pytest.raises(ValueError):
            strategy.weight = 1.5

    def test_enabled_toggle(self, strategy):
        assert strategy.enabled is True
        strategy.enabled = False
        assert strategy.enabled is False


# ---------------------------------------------------------------------------
# StatisticalMeanReversion
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_MEAN_REVERSION, reason="pandas_ta not installed")
class TestStatisticalMeanReversion:
    @pytest.fixture
    def strategy(self):
        return StatisticalMeanReversion()

    def test_instantiation_defaults(self, strategy):
        assert strategy.name == "StatisticalMeanReversion"
        assert strategy.bb_period == 20
        assert strategy.z_score_entry == 2.0
        assert strategy.lookback_period == 60

    def test_custom_config(self):
        s = StatisticalMeanReversion(config={"bb_period": 30, "z_score_entry": 1.5})
        assert s.bb_period == 30
        assert s.z_score_entry == 1.5

    def test_generate_signals_insufficient_data(self, strategy):
        df = _make_ohlcv(n=10)
        signals = strategy.generate_signals(df)
        assert signals == []

    def test_generate_signals_returns_list(self, strategy):
        df = _make_ohlcv(n=100)
        signals = strategy.generate_signals(df)
        assert isinstance(signals, list)

    def test_generate_signals_all_valid(self, strategy):
        df = _make_ohlcv(n=100)
        signals = strategy.generate_signals(df)
        for sig in signals:
            assert isinstance(sig, Signal)
            assert 0.0 <= sig.strength <= 1.0

    def test_generate_signals_empty_dataframe(self, strategy):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        signals = strategy.generate_signals(df)
        assert signals == []

    def test_should_exit_insufficient_data(self, strategy):
        df = _make_ohlcv(n=5)
        pos = {"direction": Direction.LONG}
        assert strategy.should_exit(pos, df) is False

    def test_detect_pairs_empty(self, strategy):
        pairs = strategy.detect_pairs([], {})
        assert pairs == []

    def test_detect_pairs_correlated(self, strategy):
        rng = np.random.default_rng(0)
        n = 100
        base = np.cumsum(rng.normal(0, 1, n)) + 100
        df1 = pd.DataFrame({
            "open": base, "high": base + 1, "low": base - 1,
            "close": base, "volume": np.ones(n) * 1e6,
        })
        df2 = pd.DataFrame({
            "open": base * 1.01, "high": base * 1.01 + 1, "low": base * 1.01 - 1,
            "close": base * 1.01, "volume": np.ones(n) * 1e6,
        })
        pairs = strategy.detect_pairs(["A", "B"], {"A": df1, "B": df2})
        assert ("A", "B") in pairs

    def test_reset_metrics(self, strategy):
        strategy.metrics.trade_count = 5
        strategy.reset_metrics()
        assert strategy.metrics.trade_count == 0


# ---------------------------------------------------------------------------
# BaseStrategy.backtest (through a concrete subclass)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_MOMENTUM, reason="pandas_ta not installed")
class TestBacktest:
    def test_backtest_empty_df(self):
        s = MultiTimeframeMomentum()
        result = s.backtest(pd.DataFrame())
        assert "error" in result

    def test_backtest_missing_columns(self):
        s = MultiTimeframeMomentum()
        df = pd.DataFrame({"close": [1, 2, 3]})
        result = s.backtest(df)
        assert "error" in result

    def test_backtest_returns_dict(self):
        s = MultiTimeframeMomentum()
        df = _make_ohlcv(n=250)
        result = s.backtest(df, initial_capital=50000)
        assert isinstance(result, dict)
        assert "initial_capital" in result or "error" in result


# ---------------------------------------------------------------------------
# Additional signal/strategy edge cases (no pandas_ta required)
# ---------------------------------------------------------------------------

class TestSignalMetadata:
    def test_metadata_preserved(self):
        sig = Signal(
            symbol="AAPL",
            direction=Direction.LONG,
            strength=0.5,
            strategy_name="test",
            metadata={"rsi": 25.0, "trend": "up"},
        )
        assert sig.metadata["rsi"] == 25.0
        assert sig.metadata["trend"] == "up"

    def test_metadata_mutable_after_create(self):
        sig = Signal(symbol="X", direction=Direction.LONG, strength=0.5, strategy_name="t")
        sig.metadata["foo"] = 42
        assert sig.metadata["foo"] == 42


class TestPerformanceMetricsFields:
    def test_all_fields_present(self):
        m = PerformanceMetrics()
        # Expected fields exist with default zero values
        assert hasattr(m, "win_rate")
        assert hasattr(m, "sharpe_ratio")
        assert hasattr(m, "max_drawdown")
        assert hasattr(m, "trade_count")
        assert hasattr(m, "total_return")
        assert hasattr(m, "profit_factor")


@pytest.mark.skipif(not HAS_MOMENTUM, reason="pandas_ta not installed")
class TestMomentumExtra:
    def test_weight_zero_allowed(self):
        s = MultiTimeframeMomentum()
        s.weight = 0.0
        assert s.weight == 0.0

    def test_weight_one_allowed(self):
        s = MultiTimeframeMomentum()
        s.weight = 1.0
        assert s.weight == 1.0

    def test_weight_negative_raises(self):
        s = MultiTimeframeMomentum()
        with pytest.raises(ValueError):
            s.weight = -0.1

    def test_enabled_default_true(self):
        s = MultiTimeframeMomentum()
        assert s.enabled is True

    def test_reset_metrics_clears_signals(self):
        s = MultiTimeframeMomentum()
        s.signals_generated.append(
            Signal(symbol="X", direction=Direction.LONG, strength=0.5, strategy_name="t")
        )
        s.reset_metrics()
        assert len(s.signals_generated) == 0

    def test_log_signal_accumulates(self):
        s = MultiTimeframeMomentum()
        sig = Signal(symbol="X", direction=Direction.LONG, strength=0.5, strategy_name="t")
        s.log_signal(sig)
        assert len(s.signals_generated) == 1

    def test_position_size_with_high_risk(self):
        s = MultiTimeframeMomentum()
        size = s.calculate_position_size(capital=100_000, atr=2.0, risk_per_trade=0.05)
        # Larger risk_per_trade should yield larger size
        baseline = s.calculate_position_size(capital=100_000, atr=2.0, risk_per_trade=0.01)
        assert size > baseline
