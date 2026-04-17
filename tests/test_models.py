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


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestOrderStatusEnum:
    def test_values(self):
        assert OrderStatus.PENDING == "pending"
        assert OrderStatus.FILLED == "filled"
        assert OrderStatus.CANCELLED == "cancelled"
        assert OrderStatus.REJECTED == "rejected"

    def test_all_members(self):
        assert len(OrderStatus) == 8

    def test_additional_statuses(self):
        assert OrderStatus.SUBMITTED == "submitted"
        assert OrderStatus.ACCEPTED == "accepted"
        assert OrderStatus.PARTIALLY_FILLED == "partially_filled"
        assert OrderStatus.EXPIRED == "expired"


class TestOrderSideEnum:
    def test_values(self):
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"

    def test_member_count(self):
        assert len(OrderSide) == 2


class TestPositionStatusEnum:
    def test_values(self):
        assert PositionStatus.OPEN == "open"
        assert PositionStatus.CLOSED == "closed"
        assert PositionStatus.PARTIAL == "partial"

    def test_count(self):
        assert len(PositionStatus) == 3


class TestTradeTypeEnum:
    def test_values(self):
        assert TradeType.LONG == "long"
        assert TradeType.SHORT == "short"

    def test_options_types(self):
        assert TradeType.COVERED_CALL == "covered_call"
        assert TradeType.CASH_SECURED_PUT == "cash_secured_put"


class TestSignalTypeEnum:
    def test_values(self):
        assert SignalType.BUY == "buy"
        assert SignalType.SELL == "sell"
        assert SignalType.HOLD == "hold"
        assert SignalType.EXIT == "exit"

    def test_count(self):
        assert len(SignalType) == 4


class TestAlertSeverityEnum:
    def test_values(self):
        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.ERROR == "error"

    def test_count(self):
        assert len(AlertSeverity) == 4


# ---------------------------------------------------------------------------
# Column coverage
# ---------------------------------------------------------------------------

class TestModelColumns:
    def test_order_has_columns(self):
        cols = {c.name for c in Order.__table__.columns}
        assert "symbol" in cols
        assert "side" in cols
        assert "quantity" in cols
        assert "price" in cols
        assert "status" in cols

    def test_order_has_broker_fields(self):
        cols = {c.name for c in Order.__table__.columns}
        assert "broker_order_id" in cols
        assert "broker_name" in cols
        assert "strategy_name" in cols

    def test_trade_has_columns(self):
        cols = {c.name for c in Trade.__table__.columns}
        assert "symbol" in cols
        assert "entry_price" in cols
        assert "exit_price" in cols
        assert "profit_loss" in cols

    def test_trade_has_time_fields(self):
        cols = {c.name for c in Trade.__table__.columns}
        assert "entry_time" in cols
        assert "exit_time" in cols
        assert "duration_seconds" in cols

    def test_position_has_columns(self):
        cols = {c.name for c in Position.__table__.columns}
        assert "symbol" in cols
        assert "quantity" in cols
        assert "average_entry_price" in cols

    def test_position_has_pl_fields(self):
        cols = {c.name for c in Position.__table__.columns}
        assert "unrealized_profit_loss" in cols
        assert "unrealized_profit_loss_percent" in cols
        assert "cost_basis" in cols
        assert "market_value" in cols

    def test_ohlcv_has_columns(self):
        cols = {c.name for c in OHLCV.__table__.columns}
        assert "open" in cols
        assert "high" in cols
        assert "low" in cols
        assert "close" in cols
        assert "volume" in cols

    def test_ohlcv_has_source(self):
        cols = {c.name for c in OHLCV.__table__.columns}
        assert "source" in cols
        assert "timeframe" in cols

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

    def test_strategy_performance_has_pl_columns(self):
        cols = {c.name for c in StrategyPerformance.__table__.columns}
        assert "total_profit_loss" in cols
        assert "max_drawdown_percent" in cols
        assert "sortino_ratio" in cols

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


# ---------------------------------------------------------------------------
# Primary keys / uniqueness / indexes
# ---------------------------------------------------------------------------

class TestPrimaryKeys:
    def test_order_pk_is_id(self):
        pks = [c.name for c in Order.__table__.primary_key]
        assert pks == ["id"]

    def test_trade_pk_is_id(self):
        pks = [c.name for c in Trade.__table__.primary_key]
        assert pks == ["id"]

    def test_position_pk_is_id(self):
        pks = [c.name for c in Position.__table__.primary_key]
        assert pks == ["id"]


class TestUniqueConstraints:
    def test_ohlcv_has_unique_symbol_ts(self):
        # OHLCV has UniqueConstraint("symbol", "timestamp", "timeframe")
        table_args = OHLCV.__table_args__
        assert any(
            hasattr(c, "columns") and {col.name for col in c.columns} == {"symbol", "timestamp", "timeframe"}
            for c in table_args
        )


class TestRelationships:
    def test_trade_has_entry_order_relationship(self):
        assert hasattr(Trade, "entry_order")
        assert hasattr(Trade, "exit_order")


class TestMetadataColumn:
    def test_order_metadata_via_extra_attribute(self):
        # Python attr is extra_metadata; DB column is "metadata"
        cols = {c.name for c in Order.__table__.columns}
        assert "metadata" in cols  # DB column name

    def test_alert_metadata_via_extra_attribute(self):
        cols = {c.name for c in Alert.__table__.columns}
        assert "metadata" in cols
