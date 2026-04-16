"""
Event bus implementation using PostgreSQL LISTEN/NOTIFY.
Enables inter-component communication and event-driven architecture.
"""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List
from uuid import UUID, uuid4

import asyncpg

from config.settings import settings
from loguru import logger


class EventType(str, Enum):
    """Event types for the trading system."""

    SIGNAL_GENERATED = "signal_generated"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    TRADE_COMPLETED = "trade_completed"
    RISK_ALERT = "risk_alert"
    STRATEGY_UPDATE = "strategy_update"
    SYSTEM_HEALTH = "system_health"
    PORTFOLIO_UPDATE = "portfolio_update"
    DATA_SYNC_COMPLETED = "data_sync_completed"


@dataclass
class Event:
    """Base event class."""

    event_type: EventType
    event_id: str
    timestamp: str
    source: str
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert event to JSON."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Create event from JSON."""
        data = json.loads(json_str)
        return cls(
            event_type=EventType(data["event_type"]),
            event_id=data["event_id"],
            timestamp=data["timestamp"],
            source=data["source"],
            data=data["data"],
        )


class EventBus:
    """PostgreSQL-based event bus for inter-component communication."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        self.connection: asyncpg.Connection | None = None
        self.pool: asyncpg.Pool | None = None
        self.listeners: Dict[EventType, List[Callable]] = {}
        self.running = False

    async def connect(self) -> None:
        """Connect to the database."""
        try:
            # Extract connection parameters from DATABASE_URL
            db_url = settings.database.url
            # Remove asyncpg:// prefix
            db_url = db_url.replace("postgresql+asyncpg://", "")

            # Parse connection string
            parts = db_url.split("@")
            if len(parts) == 2:
                auth, host_db = parts
                user, password = auth.split(":")
                host, db = host_db.split("/")
                host_parts = host.split(":")
                db_host = host_parts[0]
                db_port = int(host_parts[1]) if len(host_parts) > 1 else 5432
            else:
                raise ValueError("Invalid DATABASE_URL format")

            self.pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                user=user,
                password=password,
                database=db,
                min_size=1,
                max_size=10,
            )
            self.connection = await self.pool.acquire()
            logger.info("EventBus connected to PostgreSQL")
        except Exception as e:
            logger.error(f"Failed to connect EventBus to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from the database."""
        if self.connection:
            await self.pool.release(self.connection)
        if self.pool:
            await self.pool.close()
        logger.info("EventBus disconnected from PostgreSQL")

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """Subscribe to an event type.

        Args:
            event_type: Type of event to listen for
            handler: Async callable that handles the event
        """
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(handler)
        logger.debug(f"Subscribed to event: {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """Unsubscribe from an event type.

        Args:
            event_type: Type of event to stop listening for
            handler: The handler to remove
        """
        if event_type in self.listeners:
            self.listeners[event_type].remove(handler)
            logger.debug(f"Unsubscribed from event: {event_type.value}")

    async def emit(self, event: Event) -> None:
        """Emit an event to PostgreSQL.

        Args:
            event: Event to emit
        """
        try:
            # Use the event_type as channel name
            channel = event.event_type.value
            payload = event.to_json()

            # Get a connection from the pool
            async with self.pool.acquire() as conn:
                await conn.execute(
                    f"NOTIFY {channel}, E'{payload.replace(chr(39), chr(39) + chr(39))}'"
                )

            logger.debug(f"Event emitted: {event.event_type.value}")

            # Also trigger local handlers
            await self._trigger_local_handlers(event)
        except Exception as e:
            logger.error(f"Failed to emit event {event.event_type}: {e}")

    async def _trigger_local_handlers(self, event: Event) -> None:
        """Trigger local event handlers."""
        handlers = self.listeners.get(event.event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.event_type}: {e}")

    async def start_listening(self) -> None:
        """Start listening for events from PostgreSQL."""
        if self.running:
            logger.warning("Event bus is already listening")
            return

        self.running = True
        logger.info("EventBus started listening for events")

        try:
            # Create a listener connection
            listener_conn = await self.pool.acquire()

            # Subscribe to all event channels
            for event_type in EventType:
                await listener_conn.add_listener(event_type.value, self._on_event)

            # Keep listening
            while self.running:
                await asyncio.sleep(1)

            # Cleanup
            for event_type in EventType:
                await listener_conn.remove_listener(event_type.value, self._on_event)
            await self.pool.release(listener_conn)

        except Exception as e:
            logger.error(f"Error in event listener: {e}")
            self.running = False

    async def stop_listening(self) -> None:
        """Stop listening for events."""
        self.running = False
        logger.info("EventBus stopped listening")

    def _on_event(self, connection: asyncpg.Connection, pid: int, channel: str, payload: str) -> None:
        """Handle incoming event from PostgreSQL.

        Args:
            connection: Database connection
            pid: Process ID
            channel: Channel name (event type)
            payload: Event payload as JSON
        """
        try:
            event = Event.from_json(payload)
            # Schedule async handlers
            asyncio.create_task(self._trigger_local_handlers(event))
        except Exception as e:
            logger.error(f"Failed to process event from channel {channel}: {e}")

    async def emit_signal_generated(
        self,
        symbol: str,
        signal_type: str,
        strategy_name: str,
        confidence: float,
        price: float,
        reason: str = "",
    ) -> None:
        """Emit a signal generated event.

        Args:
            symbol: Trading symbol
            signal_type: Type of signal (buy/sell/hold/exit)
            strategy_name: Name of the strategy
            confidence: Confidence score (0-1)
            price: Current price
            reason: Optional reason for the signal
        """
        event = Event(
            event_type=EventType.SIGNAL_GENERATED,
            event_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source="strategy_engine",
            data={
                "symbol": symbol,
                "signal_type": signal_type,
                "strategy_name": strategy_name,
                "confidence": confidence,
                "price": price,
                "reason": reason,
            },
        )
        await self.emit(event)

    async def emit_order_placed(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        strategy_name: str,
    ) -> None:
        """Emit an order placed event."""
        event = Event(
            event_type=EventType.ORDER_PLACED,
            event_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source="execution_engine",
            data={
                "order_id": str(order_id),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "strategy_name": strategy_name,
            },
        )
        await self.emit(event)

    async def emit_order_filled(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        fill_price: float,
        strategy_name: str,
    ) -> None:
        """Emit an order filled event."""
        event = Event(
            event_type=EventType.ORDER_FILLED,
            event_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source="execution_engine",
            data={
                "order_id": str(order_id),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "fill_price": fill_price,
                "strategy_name": strategy_name,
            },
        )
        await self.emit(event)

    async def emit_risk_alert(
        self,
        alert_type: str,
        title: str,
        message: str,
        severity: str = "warning",
        symbol: str = "",
        strategy_name: str = "",
    ) -> None:
        """Emit a risk alert event."""
        event = Event(
            event_type=EventType.RISK_ALERT,
            event_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source="risk_manager",
            data={
                "alert_type": alert_type,
                "title": title,
                "message": message,
                "severity": severity,
                "symbol": symbol,
                "strategy_name": strategy_name,
            },
        )
        await self.emit(event)

    async def emit_system_health(
        self,
        status: str,
        uptime_seconds: float,
        active_positions: int,
        active_orders: int,
        memory_usage_percent: float,
    ) -> None:
        """Emit a system health event."""
        event = Event(
            event_type=EventType.SYSTEM_HEALTH,
            event_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source="system_monitor",
            data={
                "status": status,
                "uptime_seconds": uptime_seconds,
                "active_positions": active_positions,
                "active_orders": active_orders,
                "memory_usage_percent": memory_usage_percent,
            },
        )
        await self.emit(event)

    async def emit_portfolio_update(
        self,
        total_value: float,
        cash: float,
        positions_value: float,
        unrealized_gain_loss: float,
        return_percent: float,
    ) -> None:
        """Emit a portfolio update event."""
        event = Event(
            event_type=EventType.PORTFOLIO_UPDATE,
            event_id=str(uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            source="portfolio_manager",
            data={
                "total_value": total_value,
                "cash": cash,
                "positions_value": positions_value,
                "unrealized_gain_loss": unrealized_gain_loss,
                "return_percent": return_percent,
            },
        )
        await self.emit(event)


# Global event bus instance
event_bus = EventBus()


async def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    return event_bus
