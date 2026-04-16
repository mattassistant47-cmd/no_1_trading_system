"""
SQLAlchemy ORM models for the trading system.
Uses async support with proper indexing and relationships.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()


class OrderStatus(str, PyEnum):
    """Order status enumeration."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(str, PyEnum):
    """Order side enumeration."""

    BUY = "buy"
    SELL = "sell"


class PositionStatus(str, PyEnum):
    """Position status enumeration."""

    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


class TradeType(str, PyEnum):
    """Trade type enumeration."""

    LONG = "long"
    SHORT = "short"
    COVERED_CALL = "covered_call"
    CASH_SECURED_PUT = "cash_secured_put"


class SignalType(str, PyEnum):
    """Signal type enumeration."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class AlertSeverity(str, PyEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"


class Order(Base):
    """Order model for tracking buy/sell orders."""

    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_order_id = Column(String(255), nullable=True, unique=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(Enum(OrderSide), nullable=False)
    order_type = Column(String(50), nullable=False)  # "market", "limit", "stop_loss"
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(15, 2), nullable=True)
    filled_quantity = Column(Numeric(20, 8), default=0)
    filled_price = Column(Numeric(15, 2), nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, index=True)
    commission = Column(Numeric(15, 2), default=0)
    slippage = Column(Numeric(15, 2), default=0)
    strategy_name = Column(String(100), nullable=False, index=True)
    broker_name = Column(String(50), nullable=False)  # "alpaca", "ibkr", "polymarket"
    extra_metadata = Column("metadata", JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    filled_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_orders_symbol_status", "symbol", "status"),
        Index("idx_orders_strategy_created", "strategy_name", "created_at"),
        Index("idx_orders_broker_order_id", "broker_order_id"),
    )


class Trade(Base):
    """Trade model for completed trades."""

    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    trade_type = Column(Enum(TradeType), nullable=False)
    entry_price = Column(Numeric(15, 2), nullable=False)
    exit_price = Column(Numeric(15, 2), nullable=True)
    quantity = Column(Numeric(20, 8), nullable=False)
    entry_quantity = Column(Numeric(20, 8), nullable=False)
    exit_quantity = Column(Numeric(20, 8), default=0)
    profit_loss = Column(Numeric(15, 2), nullable=True)
    profit_loss_percent = Column(Float, nullable=True)
    win = Column(Boolean, default=False)
    strategy_name = Column(String(100), nullable=False, index=True)
    broker_name = Column(String(50), nullable=False)
    entry_order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    exit_order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    duration_seconds = Column(BigInteger, nullable=True)
    extra_metadata = Column("metadata", JSONB, default={})
    entry_time = Column(DateTime(timezone=True), nullable=False, index=True)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    entry_order = relationship("Order", foreign_keys=[entry_order_id])
    exit_order = relationship("Order", foreign_keys=[exit_order_id])

    __table_args__ = (
        Index("idx_trades_symbol_strategy", "symbol", "strategy_name"),
        Index("idx_trades_entry_time", "entry_time"),
        Index("idx_trades_win", "win"),
    )


class Position(Base):
    """Position model for tracking open positions."""

    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    quantity = Column(Numeric(20, 8), nullable=False)
    average_entry_price = Column(Numeric(15, 2), nullable=False)
    current_price = Column(Numeric(15, 2), nullable=False)
    cost_basis = Column(Numeric(15, 2), nullable=False)
    market_value = Column(Numeric(15, 2), nullable=False)
    unrealized_profit_loss = Column(Numeric(15, 2), nullable=True)
    unrealized_profit_loss_percent = Column(Float, nullable=True)
    status = Column(Enum(PositionStatus), default=PositionStatus.OPEN)
    strategy_name = Column(String(100), nullable=False, index=True)
    broker_name = Column(String(50), nullable=False)
    stop_loss_price = Column(Numeric(15, 2), nullable=True)
    take_profit_price = Column(Numeric(15, 2), nullable=True)
    extra_metadata = Column("metadata", JSONB, default={})
    opened_at = Column(DateTime(timezone=True), nullable=False, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_positions_symbol_strategy", "symbol", "strategy_name"),
        Index("idx_positions_status", "status"),
    )


class OHLCV(Base):
    """OHLCV data model - TimescaleDB hypertable for time-series data."""

    __tablename__ = "ohlcv"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Numeric(15, 8), nullable=False)
    high = Column(Numeric(15, 8), nullable=False)
    low = Column(Numeric(15, 8), nullable=False)
    close = Column(Numeric(15, 8), nullable=False)
    volume = Column(BigInteger, nullable=False)
    vwap = Column(Numeric(15, 8), nullable=True)
    timeframe = Column(String(10), default="1d")  # "1m", "5m", "1h", "1d"
    source = Column(String(50), nullable=False)  # "alpaca", "polygon", "ibkr"
    extra_metadata = Column("metadata", JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "timeframe", name="uq_ohlcv_symbol_timestamp"),
        Index("idx_ohlcv_symbol_timestamp", "symbol", "timestamp"),
        Index("idx_ohlcv_timestamp", "timestamp"),
    )


class Signal(Base):
    """Trading signal model."""

    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    signal_type = Column(Enum(SignalType), nullable=False)
    strategy_name = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, default=0.5)
    score = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    price_at_signal = Column(Numeric(15, 2), nullable=False)
    extra_metadata = Column("metadata", JSONB, default={})
    acted_upon = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_signals_symbol_strategy", "symbol", "strategy_name"),
        Index("idx_signals_created", "created_at"),
    )


class Alert(Base):
    """System alert model for risk and operational alerts."""

    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    severity = Column(Enum(AlertSeverity), nullable=False)
    alert_type = Column(String(100), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    symbol = Column(String(20), nullable=True, index=True)
    strategy_name = Column(String(100), nullable=True)
    extra_metadata = Column("metadata", JSONB, default={})
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_alerts_severity_created", "severity", "created_at"),
        Index("idx_alerts_type_created", "alert_type", "created_at"),
    )


class StrategyPerformance(Base):
    """Strategy performance metrics."""

    __tablename__ = "strategy_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_name = Column(String(100), nullable=False, unique=True, index=True)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    total_profit_loss = Column(Numeric(15, 2), default=0)
    avg_profit_loss = Column(Numeric(15, 2), default=0)
    profit_factor = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    sortino_ratio = Column(Float, nullable=True)
    max_drawdown_percent = Column(Float, nullable=True)
    consecutive_wins = Column(Integer, default=0)
    consecutive_losses = Column(Integer, default=0)
    max_consecutive_losses = Column(Integer, default=0)
    avg_holding_time_seconds = Column(BigInteger, nullable=True)
    largest_win = Column(Numeric(15, 2), nullable=True)
    largest_loss = Column(Numeric(15, 2), nullable=True)
    extra_metadata = Column("metadata", JSONB, default={})
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class SystemLog(Base):
    """System event log for audit and debugging."""

    __tablename__ = "system_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level = Column(String(20), index=True)  # "DEBUG", "INFO", "WARNING", "ERROR"
    module = Column(String(100), nullable=False, index=True)
    message = Column(Text, nullable=False)
    exception = Column(Text, nullable=True)
    extra_metadata = Column("metadata", JSONB, default={})
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_logs_level_timestamp", "level", "timestamp"),
        Index("idx_logs_module_timestamp", "module", "timestamp"),
    )


class PortfolioSnapshot(Base):
    """Portfolio snapshot for historical tracking."""

    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    total_value = Column(Numeric(15, 2), nullable=False)
    cash = Column(Numeric(15, 2), nullable=False)
    positions_value = Column(Numeric(15, 2), nullable=False)
    unrealized_gain_loss = Column(Numeric(15, 2), nullable=False)
    total_profit_loss = Column(Numeric(15, 2), nullable=False)
    return_percent = Column(Float, nullable=False)
    leverage = Column(Float, default=1.0)
    num_open_positions = Column(Integer, default=0)
    num_open_orders = Column(Integer, default=0)
    extra_metadata = Column("metadata", JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_portfolio_snapshots_timestamp", "timestamp"),
    )
