"""
Abstract base broker class for multi-asset trading system.

Defines the interface that all broker implementations must follow.
Supports stocks, crypto, options, and futures trading.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List, Callable, Dict, Any
import pandas as pd
from loguru import logger


class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    """Time in force enumeration."""
    DAY = "day"
    GTC = "gtc"  # Good-til-canceled
    OPG = "opg"  # Market on open
    CLS = "cls"  # Market on close
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclass
class Account:
    """Account information."""
    account_id: str
    balance: float
    buying_power: float
    equity: float
    cash: float
    margin_available: Optional[float] = None
    multiplier: float = 1.0
    account_type: str = "unknown"
    broker_name: str = "unknown"
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class Position:
    """Position information."""
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float
    position_type: str = "long"  # long or short
    asset_class: str = "stock"  # stock, crypto, option, future
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class Order:
    """Order information."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    avg_fill_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    created_at: datetime = None
    updated_at: datetime = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


@dataclass
class Quote:
    """Real-time quote data."""
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    last_price: float
    last_size: float
    timestamp: datetime
    volume: Optional[float] = None


class BaseBroker(ABC):
    """
    Abstract base class for broker implementations.

    All broker adapters must inherit from this class and implement
    all abstract methods. Supports synchronous operations with async ready.
    """

    def __init__(self, name: str, **config):
        """
        Initialize broker with configuration.

        Args:
            name: Broker name identifier
            **config: Broker-specific configuration parameters
        """
        self.name = name
        self.config = config
        self._connected = False
        logger.info(f"Initializing {name} broker with config keys: {list(config.keys())}")

    # Properties
    @property
    def broker_name(self) -> str:
        """Get broker name."""
        return self.name

    @property
    @abstractmethod
    def supports_options(self) -> bool:
        """Whether this broker supports options trading."""
        pass

    @property
    @abstractmethod
    def supports_crypto(self) -> bool:
        """Whether this broker supports cryptocurrency trading."""
        pass

    @property
    def is_connected(self) -> bool:
        """Whether broker connection is active."""
        return self._connected

    # Connection management
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to broker.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close broker connection.

        Returns:
            True if disconnection successful
        """
        pass

    # Account information
    @abstractmethod
    async def get_account(self) -> Account:
        """
        Get current account information.

        Returns:
            Account object with balance, buying power, equity info
        """
        pass

    # Position management
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects
        """
        pass

    # Order management
    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """
        Submit an order to the broker.

        Args:
            symbol: Asset symbol (e.g., 'AAPL', 'BTC/USD')
            qty: Order quantity
            side: OrderSide.BUY or OrderSide.SELL
            order_type: OrderType (MARKET, LIMIT, STOP, STOP_LIMIT)
            time_in_force: TimeInForce (DAY, GTC, IOC, FOK)
            limit_price: Limit price for LIMIT and STOP_LIMIT orders
            stop_price: Stop price for STOP and STOP_LIMIT orders

        Returns:
            Order object with order_id and status

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If order submission fails
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation successful, False if order not found or already filled
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """
        Get status of an order.

        Args:
            order_id: Order ID to check

        Returns:
            Order object with current status
        """
        pass

    # Market data
    @abstractmethod
    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data.

        Args:
            symbol: Asset symbol
            timeframe: Timeframe ('1min', '5min', '15min', '1h', '1d', etc.)
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        pass

    @abstractmethod
    async def stream_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], None],
    ) -> None:
        """
        Stream real-time quotes for symbols.

        Callback function is invoked for each quote update.
        This is a blocking operation; run in separate task for continuous streaming.

        Args:
            symbols: List of symbols to stream
            callback: Async or sync function to call with Quote objects

        Example:
            async def quote_handler(quote: Quote):
                print(f"{quote.symbol}: {quote.bid} x {quote.ask}")

            await broker.stream_quotes(['AAPL', 'BTC/USD'], quote_handler)
        """
        pass

    # Utility methods
    async def _validate_symbol(self, symbol: str) -> bool:
        """
        Validate that symbol is tradeable on this broker.

        Args:
            symbol: Symbol to validate

        Returns:
            True if valid, False otherwise
        """
        if not symbol or not isinstance(symbol, str):
            return False
        return len(symbol) > 0 and len(symbol) <= 20

    async def _validate_order_params(
        self,
        qty: float,
        order_type: OrderType,
        limit_price: Optional[float],
        stop_price: Optional[float],
    ) -> None:
        """
        Validate order parameters.

        Args:
            qty: Order quantity
            order_type: Order type
            limit_price: Limit price (if applicable)
            stop_price: Stop price (if applicable)

        Raises:
            ValueError: If parameters are invalid
        """
        if qty <= 0:
            raise ValueError(f"Quantity must be positive, got {qty}")

        if order_type == OrderType.LIMIT and not limit_price:
            raise ValueError("LIMIT order requires limit_price")

        if order_type == OrderType.STOP and not stop_price:
            raise ValueError("STOP order requires stop_price")

        if order_type == OrderType.STOP_LIMIT and (not limit_price or not stop_price):
            raise ValueError("STOP_LIMIT order requires both limit_price and stop_price")

        if limit_price and limit_price <= 0:
            raise ValueError(f"Limit price must be positive, got {limit_price}")

        if stop_price and stop_price <= 0:
            raise ValueError(f"Stop price must be positive, got {stop_price}")


__all__ = [
    "BaseBroker",
    "Account",
    "Position",
    "Order",
    "Quote",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
]
