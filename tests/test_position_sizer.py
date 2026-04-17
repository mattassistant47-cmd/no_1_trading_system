"""Tests for PositionSizer in risk/position_sizer.py."""
import pytest

from risk.position_sizer import (
    PositionSizer,
    SignalMetrics,
    SizingMethod,
    SizingResult,
)


def _signal(
    symbol: str = "AAPL",
    signal_strength: float = 0.8,
    win_rate: float = 0.6,
    avg_win: float = 100.0,
    avg_loss: float = 50.0,
    volatility: float = 0.20,
    atr: float = 2.0,
    current_price: float = 150.0,
    entry_price: float = 150.0,
    stop_loss: float = 145.0,
) -> SignalMetrics:
    return SignalMetrics(
        symbol=symbol,
        signal_strength=signal_strength,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        volatility=volatility,
        atr=atr,
        current_price=current_price,
        entry_price=entry_price,
        stop_loss=stop_loss,
    )


class TestPositionSizerInit:
    def test_defaults(self):
        s = PositionSizer()
        assert s.kelly_fraction == 0.25
        assert s.max_position_size == 10000
        assert s.min_position_size == 1

    def test_custom_params(self):
        s = PositionSizer(kelly_fraction=0.5, max_position_size=500, min_position_size=10)
        assert s.kelly_fraction == 0.5
        assert s.max_position_size == 500
        assert s.min_position_size == 10


class TestKellyFull:
    async def test_returns_sizing_result(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_size(_signal(), 100_000, method=SizingMethod.KELLY_FULL)
        assert isinstance(result, SizingResult)
        assert result.method == SizingMethod.KELLY_FULL

    async def test_positive_edge_produces_size(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_size(_signal(), 100_000, method=SizingMethod.KELLY_FULL)
        assert result.quantity >= 1
        assert result.kelly_fraction is not None
        assert 0.0 <= result.kelly_fraction <= 0.25

    async def test_zero_avg_win_returns_zero_quantity(self):
        s = PositionSizer()
        sig = _signal(avg_win=0.0)
        result = await s.calculate_size(sig, 100_000, method=SizingMethod.KELLY_FULL)
        assert result.quantity == 0

    async def test_zero_avg_loss_returns_zero(self):
        s = PositionSizer()
        sig = _signal(avg_loss=0.0)
        result = await s.calculate_size(sig, 100_000, method=SizingMethod.KELLY_FULL)
        assert result.quantity == 0


class TestKellyFractional:
    async def test_produces_smaller_size_than_full(self):
        s = PositionSizer(kelly_fraction=0.25, max_position_size=1_000_000)
        full = await s.calculate_size(_signal(), 100_000, method=SizingMethod.KELLY_FULL)
        frac = await s.calculate_size(_signal(), 100_000, method=SizingMethod.KELLY_FRACTIONAL)
        assert frac.quantity <= full.quantity

    async def test_method_is_fractional(self):
        s = PositionSizer()
        result = await s.calculate_size(
            _signal(), 100_000, method=SizingMethod.KELLY_FRACTIONAL
        )
        assert result.method == SizingMethod.KELLY_FRACTIONAL


class TestATRBased:
    async def test_returns_sizing_result(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_size(_signal(), 100_000, method=SizingMethod.ATR_BASED)
        assert isinstance(result, SizingResult)
        assert result.method == SizingMethod.ATR_BASED

    async def test_zero_atr_returns_zero(self):
        s = PositionSizer()
        sig = _signal(atr=0.0)
        result = await s.calculate_size(sig, 100_000, method=SizingMethod.ATR_BASED)
        assert result.quantity == 0

    async def test_higher_atr_smaller_position(self):
        s = PositionSizer(max_position_size=1_000_000)
        small = await s.calculate_size(_signal(atr=1.0), 100_000, method=SizingMethod.ATR_BASED)
        large = await s.calculate_size(_signal(atr=10.0), 100_000, method=SizingMethod.ATR_BASED)
        assert small.quantity >= large.quantity


class TestFixedRisk:
    async def test_method(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_size(_signal(), 100_000, method=SizingMethod.FIXED_RISK)
        assert result.method == SizingMethod.FIXED_RISK

    async def test_invalid_stop_loss_returns_zero(self):
        s = PositionSizer()
        sig = _signal(current_price=100.0, stop_loss=100.0)  # zero risk per unit
        result = await s.calculate_size(sig, 100_000, method=SizingMethod.FIXED_RISK)
        assert result.quantity == 0


class TestVolatilityAdjusted:
    async def test_method(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_size(
            _signal(), 100_000, method=SizingMethod.VOLATILITY_ADJUSTED
        )
        assert result.method == SizingMethod.VOLATILITY_ADJUSTED


class TestBounds:
    async def test_max_position_cap(self):
        s = PositionSizer(max_position_size=5)
        result = await s.calculate_size(_signal(), 1_000_000_000, method=SizingMethod.KELLY_FULL)
        assert result.quantity <= 5

    async def test_min_position_floor(self):
        s = PositionSizer(min_position_size=7)
        # Very tiny equity, should still get at least min
        result = await s.calculate_size(_signal(), 1.0, method=SizingMethod.KELLY_FULL)
        assert result.quantity >= 7


class TestCalculateMaxPosition:
    async def test_returns_sizing_result(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_max_position(
            account_equity=100_000,
            current_price=100.0,
            max_position_pct=5.0,
            max_loss_pct=1.0,
            stop_loss=95.0,
        )
        assert isinstance(result, SizingResult)

    async def test_no_stop_loss_uses_max_position(self):
        s = PositionSizer(max_position_size=1_000_000)
        result = await s.calculate_max_position(
            account_equity=100_000,
            current_price=100.0,
            max_position_pct=5.0,
            max_loss_pct=1.0,
            stop_loss=None,
        )
        assert result.quantity > 0


class TestUnknownMethod:
    async def test_unknown_method_raises(self):
        s = PositionSizer()
        with pytest.raises(ValueError):
            await s.calculate_size(_signal(), 100_000, method="nonsense")


class TestSizingResult:
    async def test_has_rationale(self):
        s = PositionSizer(max_position_size=1_000_000)
        r = await s.calculate_size(_signal(), 100_000, method=SizingMethod.KELLY_FULL)
        assert isinstance(r.rationale, str)
        assert r.rationale != ""
