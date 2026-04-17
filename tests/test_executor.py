"""Tests for OrderExecutor in core/executor.py.

These tests only exercise tracking/cancellation behavior — the DB-mutating
`_on_fill` / `_on_terminal` paths require the full Postgres-backed schema
(JSONB, ARRAY etc.) and are covered indirectly by integration tests.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from brokers.base import BaseBroker, Order as BrokerOrder, OrderSide, OrderStatus, OrderType
from core.executor import OrderExecutor


class _FakeBaseBroker(BaseBroker):
    @property
    def supports_options(self): return False

    @property
    def supports_crypto(self): return False

    def __init__(self):
        super().__init__("fake")
        self._connected = True
        self._status_map = {}
        self._cancelled = []

    async def connect(self): return True
    async def disconnect(self): self._connected = False; return True
    async def get_account(self): raise NotImplementedError
    async def get_positions(self): return []
    async def submit_order(self, *a, **kw): raise NotImplementedError
    async def cancel_order(self, order_id):
        self._cancelled.append(order_id)
        return True
    async def get_order_status(self, order_id):
        return self._status_map.get(order_id)
    async def get_historical_bars(self, *a, **kw): raise NotImplementedError
    async def stream_quotes(self, *a, **kw): raise NotImplementedError


def _mk_status(status: OrderStatus, **kw) -> BrokerOrder:
    return BrokerOrder(
        order_id=kw.get("order_id", "o-1"),
        symbol=kw.get("symbol", "AAPL"),
        side=kw.get("side", OrderSide.BUY),
        order_type=OrderType.MARKET,
        quantity=kw.get("quantity", 10),
        filled_quantity=kw.get("filled_quantity", 0),
        status=status,
        avg_fill_price=kw.get("avg_fill_price"),
    )


class TestTrackOrder:
    async def test_track_order_adds_to_list(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        await ex.track_order("o-1", "alpaca", symbol="AAPL", side="buy", quantity=10, price=150.0)
        assert len(ex.pending_orders) == 1
        assert ex.pending_orders[0]["id"] == "o-1"

    async def test_track_multiple_orders(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        await ex.track_order("o-1", "alpaca")
        await ex.track_order("o-2", "alpaca")
        await ex.track_order("o-3", "alpaca")
        assert len(ex.pending_orders) == 3

    async def test_track_order_captures_metadata(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        await ex.track_order("o-1", "alpaca", symbol="BTC/USD", strategy_name="momentum")
        entry = ex.pending_orders[0]
        assert entry["symbol"] == "BTC/USD"
        assert entry["strategy_name"] == "momentum"


class TestCheckFillsEmpty:
    async def test_no_pending_no_op(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        await ex.check_fills()  # should not raise
        assert ex.pending_orders == []


class TestCheckFillsBrokerMissing:
    async def test_broker_not_registered_kept_pending(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        await ex.track_order("o-1", "alpaca")
        await ex.check_fills()
        # Order kept in pending list because broker is missing
        assert len(ex.pending_orders) == 1


class TestCheckFillsDisconnected:
    async def test_disconnected_broker_kept_pending(self):
        broker = _FakeBaseBroker()
        broker._connected = False
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        await ex.track_order("o-1", "alpaca")
        await ex.check_fills()
        assert len(ex.pending_orders) == 1


class TestCheckFillsTerminalStates:
    async def test_cancelled_order_removed_after_update(self):
        broker = _FakeBaseBroker()
        broker._status_map["o-1"] = _mk_status(OrderStatus.CANCELLED)
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        # Skip DB write path
        ex._on_terminal = AsyncMock()
        await ex.track_order("o-1", "alpaca")
        await ex.check_fills()
        assert ex._on_terminal.called
        assert ex.pending_orders == []

    async def test_rejected_order_removed(self):
        broker = _FakeBaseBroker()
        broker._status_map["o-2"] = _mk_status(OrderStatus.REJECTED, order_id="o-2")
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        ex._on_terminal = AsyncMock()
        await ex.track_order("o-2", "alpaca")
        await ex.check_fills()
        assert ex.pending_orders == []

    async def test_expired_order_removed(self):
        broker = _FakeBaseBroker()
        broker._status_map["o-3"] = _mk_status(OrderStatus.EXPIRED, order_id="o-3")
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        ex._on_terminal = AsyncMock()
        await ex.track_order("o-3", "alpaca")
        await ex.check_fills()
        assert ex.pending_orders == []


class TestCheckFillsFilled:
    async def test_filled_order_triggers_on_fill_and_removes(self):
        broker = _FakeBaseBroker()
        broker._status_map["o-4"] = _mk_status(
            OrderStatus.FILLED, order_id="o-4", filled_quantity=10, avg_fill_price=150.0
        )
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        ex._on_fill = AsyncMock()
        await ex.track_order("o-4", "alpaca", symbol="AAPL", side="buy", quantity=10, price=150.0)
        await ex.check_fills()
        assert ex._on_fill.called
        assert ex.pending_orders == []


class TestCheckFillsOpenStays:
    async def test_open_order_stays_pending(self):
        broker = _FakeBaseBroker()
        broker._status_map["o-5"] = _mk_status(OrderStatus.OPEN, order_id="o-5")
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        await ex.track_order("o-5", "alpaca")
        await ex.check_fills()
        assert len(ex.pending_orders) == 1


class TestCheckFillsBrokerException:
    async def test_broker_exception_does_not_kill_loop(self):
        broker = _FakeBaseBroker()
        async def boom(order_id):
            raise RuntimeError("network down")
        broker.get_order_status = boom
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        await ex.track_order("o-6", "alpaca")
        # Should not raise
        await ex.check_fills()
        assert len(ex.pending_orders) == 1


class TestCancelAll:
    async def test_cancels_all_pending(self):
        broker = _FakeBaseBroker()
        ex = OrderExecutor(brokers={"alpaca": broker}, event_bus=MagicMock())
        await ex.track_order("o-a", "alpaca")
        await ex.track_order("o-b", "alpaca")
        count = await ex.cancel_all()
        assert count == 2
        assert ex.pending_orders == []
        assert set(broker._cancelled) == {"o-a", "o-b"}

    async def test_cancel_all_empty(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        count = await ex.cancel_all()
        assert count == 0

    async def test_cancel_all_skips_missing_broker(self):
        ex = OrderExecutor(brokers={}, event_bus=MagicMock())
        await ex.track_order("o-x", "nonexistent")
        count = await ex.cancel_all()
        assert count == 0
        # Pending list cleared regardless
        assert ex.pending_orders == []
