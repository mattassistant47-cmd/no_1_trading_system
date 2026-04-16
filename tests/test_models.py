"""Tests for ORM models and enums in core/models.py."""
import pytest

from core.models import (
    Base,
    Order,
    Trade,
    Position,
    OHLCV,
    Signal,
    Alert,
    StrategyPerformance,
    SystemLog,
    PortfolioSnapshot,
    OrderStatus,
    OrderSide,
    PositionStatus,
    TradeType,
    SignalType,
    AlertSeverity,
)


class TestTableNames:
    def test_expected_tables_in_metadata(self):
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "orders",
            "trades",
            "positions",
            "ohlcv",
            "signals",
            "alerts",
            "strategy_performance",
            "system_logs",
            "portfolio_snapshots",
        }
        assert expected.issubset(table_names)


class TestOrderStatusEnum:
    def test_values(self):
        assert OrderStatus.PENDING == "pending"
        assert OrderStatus.FILLED == "filled"
        assert OrderStatus.CANCELLED == "cancelled"
        assert OrderStatus.REJECTED == "rejected"

    def test_all_members(self):
        assert len(OrderStatus) == 8


class TestOrderSideEnum:
    def test_values(self):
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"


class TestPositionStatusEnum:
    def test_values(self):
        assert PositionStatus.OPEN == "open"
        assert PositionStatus.CLOSED == "closed"
        assert PositionStatus.PARTIAL == "partial"


class TestTradeTypeEnum:
    def test_values(self):
        assert TradeType.LONG == "long"
        assert TradeType.SHORT == "short"


class TestSignalTypeEnum:
    def test_values(self):
        assert SignalType.BUY == "buy"
        assert SignalType.SELL == "sell"
        assert SignalType.HOLD == "hold"
        assert SignalType.EXIT == "exit"


class TestAlertSeverityEnum:
    def test_values(self):
        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.ERROR == "error"


class TestModelColumns:
    def test_order_has_columns(self):
        cols = {c.name for c in Order.__table__.columns}
        assert "symbol" in cols
        assert "side" in cols
        assert "quantity" in cols
        assert "price" in cols
        assert "status" in cols

    def test_trade_has_columns(self):
        cols = {c.name for c in Trade.__table__.columns}
        assert "symbol" in cols
        assert "entry_price" in cols
        assert "exit_price" in cols
        assert "profit_loss" in cols

    def test_position_has_columns(self):
        cols = {c.name for c in Position.__table__.columns}
        assert "symbol" in cols
        assert "quantity" in cols
        assert "average_entry_price" in cols

    def test_ohlcv_has_columns(self):
        cols = {c.name for c in OHLCV.__table__.columns}
        assert "open" in cols
        assert "high" in cols
        assert "low" in cols
        assert "close" in cols
        assert "volume" in cols

    def test_signal_has_columns(self):
        cols = {c.name for c in Signal.__table__.columns}
        assert "symbol" in cols
        assert "signal_type" in cols
        assert "confidence" in cols

    def test_alert_has_columns(self):
        cols = {c.name for c in Alert.__table__.columns}
        assert "severity" in cols
        assert "title" in cols
        assert "message" in cols

    def test_strategy_performance_has_columns(self):
        cols = {c.name for c in StrategyPerformance.__table__.columns}
        assert "strategy_name" in cols
        assert "win_rate" in cols
        assert "sharpe_ratio" in cols

    def test_system_log_has_columns(self):
        cols = {c.name for c in SystemLog.__table__.columns}
        assert "level" in cols
        assert "module" in cols
        assert "message" in cols

    def test_portfolio_snapshot_has_columns(self):
        cols = {c.name for c in PortfolioSnapshot.__table__.columns}
        assert "total_value" in cols
        assert "cash" in cols
        assert "return_percent" in cols
