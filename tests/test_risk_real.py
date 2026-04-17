"""Tests for the real RiskManager, Order, Position classes."""
import pytest
from datetime import datetime

from risk.manager import (
    RiskManager,
    Order,
    Position,
    PortfolioRisk,
    AssetClass,
    OrderType,
)


# ---------------------------------------------------------------------------
# Dataclass creation
# ---------------------------------------------------------------------------

class TestOrder:
    def test_create_order(self):
        o = Order(
            symbol="AAPL",
            quantity=100,
            price=150.0,
            side=OrderType.BUY,
            asset_class=AssetClass.EQUITY,
        )
        assert o.symbol == "AAPL"
        assert o.quantity == 100
        assert o.price == 150.0
        assert o.side == OrderType.BUY
        assert o.asset_class == AssetClass.EQUITY
        assert isinstance(o.timestamp, datetime)
        assert o.portfolio_pct == 0.0

    def test_order_with_strategy_id(self):
        o = Order(
            symbol="BTC",
            quantity=0.5,
            price=60000.0,
            side=OrderType.BUY,
            asset_class=AssetClass.CRYPTO,
            strategy_id="momentum_v1",
        )
        assert o.strategy_id == "momentum_v1"


class TestPosition:
    def test_create_position(self):
        p = Position(
            symbol="MSFT",
            quantity=50,
            entry_price=300.0,
            current_price=310.0,
            asset_class=AssetClass.EQUITY,
        )
        assert p.symbol == "MSFT"
        assert p.pnl == 0.0  # not yet updated

    def test_update_pnl(self):
        p = Position(
            symbol="MSFT",
            quantity=50,
            entry_price=300.0,
            current_price=310.0,
            asset_class=AssetClass.EQUITY,
        )
        p.update_pnl()
        assert p.pnl == pytest.approx(500.0)
        assert p.pnl_pct == pytest.approx(10.0 / 300.0)

    def test_notional_value(self):
        p = Position(
            symbol="AAPL",
            quantity=100,
            entry_price=150.0,
            current_price=155.0,
            asset_class=AssetClass.EQUITY,
        )
        assert p.notional_value() == pytest.approx(15500.0)

    def test_negative_pnl(self):
        p = Position(
            symbol="GOOGL",
            quantity=20,
            entry_price=140.0,
            current_price=130.0,
            asset_class=AssetClass.EQUITY,
        )
        p.update_pnl()
        assert p.pnl < 0

    def test_notional_value_short(self):
        p = Position(
            symbol="TSLA",
            quantity=-10,
            entry_price=200.0,
            current_price=190.0,
            asset_class=AssetClass.EQUITY,
        )
        # notional is absolute
        assert p.notional_value() == pytest.approx(1900.0)

    def test_zero_entry_price_no_divide_error(self):
        p = Position(
            symbol="WEIRD",
            quantity=10,
            entry_price=0.0,
            current_price=100.0,
            asset_class=AssetClass.EQUITY,
        )
        p.update_pnl()
        assert p.pnl_pct == 0.0


class TestAssetClassEnum:
    def test_values(self):
        assert AssetClass.EQUITY == "equity"
        assert AssetClass.CRYPTO == "crypto"
        assert AssetClass.OPTIONS == "options"
        assert AssetClass.PREDICTION_MARKET == "prediction_market"


class TestOrderTypeEnum:
    def test_values(self):
        assert OrderType.BUY == "buy"
        assert OrderType.SELL == "sell"
        assert OrderType.SHORT == "short"
        assert OrderType.CLOSE == "close"


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

class TestRiskManagerInstantiation:
    def test_defaults(self):
        rm = RiskManager()
        assert rm.initial_equity == 1_000_000.0
        assert rm.max_drawdown_pct == 10.0
        assert rm.max_positions == 30
        assert rm.trading_enabled is True

    def test_custom_params(self):
        rm = RiskManager(initial_equity=500_000, max_positions=10, max_leverage=2.0)
        assert rm.initial_equity == 500_000
        assert rm.max_positions == 10
        assert rm.max_leverage == 2.0


class TestRiskManagerCheckOrder:
    @pytest.fixture
    def rm(self):
        return RiskManager(initial_equity=100_000, max_single_position_pct=5.0, max_positions=3)

    async def test_approve_small_order(self, rm):
        order = Order(
            symbol="AAPL",
            quantity=5,
            price=150.0,
            side=OrderType.BUY,
            asset_class=AssetClass.EQUITY,
        )
        approved, reason = await rm.check_order(order)
        assert approved is True, f"Expected approval but got: {reason}"

    async def test_reject_oversized_position(self, rm):
        order = Order(
            symbol="AAPL",
            quantity=100,
            price=150.0,
            side=OrderType.BUY,
            asset_class=AssetClass.EQUITY,
        )
        approved, reason = await rm.check_order(order)
        assert approved is False
        assert "exceeds limit" in reason.lower() or "Position size" in reason

    async def test_reject_when_trading_disabled(self, rm):
        rm.disable_trading("test")
        order = Order(
            symbol="AAPL",
            quantity=1,
            price=150.0,
            side=OrderType.BUY,
            asset_class=AssetClass.EQUITY,
        )
        approved, reason = await rm.check_order(order)
        assert approved is False
        assert "disabled" in reason.lower()

    async def test_reject_max_positions_reached(self, rm):
        for sym in ["A", "B", "C"]:
            rm.update_position(sym, 10, 10.0, 10.0, AssetClass.EQUITY)
        order = Order(
            symbol="NEW",
            quantity=1,
            price=10.0,
            side=OrderType.BUY,
            asset_class=AssetClass.EQUITY,
        )
        approved, reason = await rm.check_order(order)
        assert approved is False
        assert "positions limit" in reason.lower() or "Max positions" in reason

    async def test_allow_existing_symbol_even_at_max(self, rm):
        for sym in ["A", "B", "C"]:
            rm.update_position(sym, 1, 10.0, 10.0, AssetClass.EQUITY)
        order = Order(
            symbol="A",
            quantity=1,
            price=10.0,
            side=OrderType.BUY,
            asset_class=AssetClass.EQUITY,
        )
        approved, _ = await rm.check_order(order)
        assert approved is True


class TestRiskManagerPositions:
    def test_update_and_close(self):
        rm = RiskManager()
        rm.update_position("AAPL", 100, 150.0, 155.0, AssetClass.EQUITY)
        assert "AAPL" in rm.positions
        rm.close_position("AAPL")
        assert "AAPL" not in rm.positions

    def test_update_existing_position(self):
        rm = RiskManager()
        rm.update_position("AAPL", 100, 150.0, 155.0, AssetClass.EQUITY)
        rm.update_position("AAPL", 200, 150.0, 160.0, AssetClass.EQUITY)
        assert rm.positions["AAPL"].quantity == 200
        assert rm.positions["AAPL"].current_price == 160.0


class TestPortfolioRisk:
    async def test_portfolio_risk_empty(self):
        rm = RiskManager(initial_equity=100_000)
        risk = await rm.get_portfolio_risk()
        assert isinstance(risk, PortfolioRisk)
        assert risk.total_positions_value == 0.0
        assert risk.current_leverage == 0.0

    async def test_portfolio_risk_with_positions(self):
        rm = RiskManager(initial_equity=100_000)
        rm.update_position("AAPL", 100, 150.0, 155.0, AssetClass.EQUITY)
        risk = await rm.get_portfolio_risk()
        assert risk.total_positions_value > 0
        assert risk.total_pnl == pytest.approx(500.0)


class TestDailyPnl:
    def test_update_and_reset(self):
        rm = RiskManager()
        rm.update_daily_pnl(-500.0)
        rm.update_daily_pnl(-300.0)
        assert rm.daily_pnl == pytest.approx(-800.0)
        rm.reset_daily_pnl()
        assert rm.daily_pnl == 0.0

    def test_enable_disable_trading(self):
        rm = RiskManager()
        rm.disable_trading("test reason")
        assert rm.trading_enabled is False
        rm.enable_trading()
        assert rm.trading_enabled is True


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestAssetClassLimits:
    async def test_crypto_allocation_limit(self):
        # Use a high max_loss_per_trade_pct so the order passes the trade-loss
        # check and specifically trips the asset-class allocation limit.
        rm = RiskManager(
            initial_equity=100_000,
            max_single_position_pct=100.0,
            max_loss_per_trade_pct=100.0,
        )
        # Default crypto limit is 20%. Trying 50% worth of crypto should fail.
        order = Order(
            symbol="BTC",
            quantity=1,
            price=50_000.0,  # 50% of equity
            side=OrderType.BUY,
            asset_class=AssetClass.CRYPTO,
        )
        approved, reason = await rm.check_order(order)
        assert approved is False
        assert "crypto" in reason.lower() or "exposure" in reason.lower()


class TestLeverage:
    async def test_leverage_breach_rejected(self):
        rm = RiskManager(
            initial_equity=100_000,
            max_leverage=1.0,
            max_single_position_pct=100.0,
        )
        # Already at full equity
        rm.update_position("AAPL", 1000, 100.0, 100.0, AssetClass.EQUITY)
        order = Order(
            symbol="BTC",
            quantity=0.5,
            price=50_000.0,
            side=OrderType.BUY,
            asset_class=AssetClass.CRYPTO,
        )
        approved, reason = await rm.check_order(order)
        assert approved is False


class TestDrawdownRecovery:
    async def test_peak_above_current_yields_drawdown(self):
        rm = RiskManager(initial_equity=100_000)
        rm.update_position("AAPL", 100, 150.0, 140.0, AssetClass.EQUITY)  # loss
        await rm.get_portfolio_risk()
        # peak_equity should still be initial_equity (>= current)
        assert rm.peak_equity >= rm.current_equity

    async def test_no_drawdown_when_peak_equals_current(self):
        rm = RiskManager(initial_equity=100_000)
        risk = await rm.get_portfolio_risk()
        assert risk.max_drawdown_pct == 0.0


class TestMultiplePositionsSameSymbol:
    def test_reupdate_replaces(self):
        rm = RiskManager()
        rm.update_position("AAPL", 10, 150.0, 150.0, AssetClass.EQUITY)
        rm.update_position("AAPL", 50, 150.0, 155.0, AssetClass.EQUITY)
        assert rm.positions["AAPL"].quantity == 50
        assert len(rm.positions) == 1


class TestExposureReport:
    async def test_empty_exposure_report(self):
        rm = RiskManager(initial_equity=100_000)
        report = await rm.get_exposure_report()
        assert "by_asset_class" in report
        assert "by_sector" in report
        assert "total_leverage" in report

    async def test_exposure_report_with_positions(self):
        rm = RiskManager(initial_equity=100_000)
        rm.update_position("AAPL", 10, 150.0, 150.0, AssetClass.EQUITY)
        report = await rm.get_exposure_report()
        equity = report["by_asset_class"]["equity"]
        assert equity["value"] > 0


class TestPortfolioRiskBreaches:
    async def test_no_breaches_initially(self):
        rm = RiskManager(initial_equity=100_000)
        risk = await rm.get_portfolio_risk()
        assert risk.max_drawdown_breach is False
        assert risk.max_daily_loss_breach is False

    async def test_large_loss_flags_daily_loss_breach(self):
        rm = RiskManager(initial_equity=100_000, max_daily_loss_pct=1.0)
        rm.update_daily_pnl(-5_000.0)  # 5% loss, breaches 1% limit
        risk = await rm.get_portfolio_risk()
        assert risk.max_daily_loss_breach is True


class TestConcentrationBreach:
    async def test_concentration_breach_flagged(self):
        rm = RiskManager(initial_equity=100_000, max_single_position_pct=5.0)
        # Create a position directly (bypassing check_order) exceeding 5%
        rm.update_position("AAPL", 100, 150.0, 150.0, AssetClass.EQUITY)  # $15k = 15%
        risk = await rm.get_portfolio_risk()
        assert risk.concentration_breach is True


class TestTradingStateIdempotent:
    def test_disable_twice_is_still_disabled(self):
        rm = RiskManager()
        rm.disable_trading("first")
        rm.disable_trading("second")
        assert rm.trading_enabled is False

    def test_enable_when_already_enabled(self):
        rm = RiskManager()
        rm.enable_trading()
        assert rm.trading_enabled is True


class TestResetRestoresTrading:
    def test_enable_after_disable(self):
        rm = RiskManager()
        rm.disable_trading("ouch")
        rm.enable_trading()
        assert rm.trading_enabled is True
