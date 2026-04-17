"""Tests for EventBus and Event dataclass in core/events.py.

Unit scope: these tests exercise in-process subscription/local-handler logic
without the Postgres LISTEN/NOTIFY pipeline. The `_trigger_local_handlers`
method is called directly so we can verify routing and error handling.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import Event, EventBus, EventType


def _make_event(
    event_type: EventType = EventType.SIGNAL_GENERATED,
    event_id: str = "evt-1",
    data: dict | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        event_id=event_id,
        timestamp="2026-01-01T00:00:00",
        source="test",
        data=data or {"key": "value"},
    )


class TestEventDataclass:
    def test_to_dict(self):
        e = _make_event()
        d = e.to_dict()
        assert d["event_type"] == EventType.SIGNAL_GENERATED
        assert d["event_id"] == "evt-1"
        assert d["data"] == {"key": "value"}

    def test_to_json_roundtrip(self):
        e = _make_event()
        payload = e.to_json()
        parsed = json.loads(payload)
        assert parsed["event_id"] == "evt-1"

    def test_from_json(self):
        e = _make_event()
        restored = Event.from_json(e.to_json())
        assert restored.event_type == e.event_type
        assert restored.event_id == e.event_id
        assert restored.data == e.data


class TestEventTypeEnum:
    def test_signal_generated(self):
        assert EventType.SIGNAL_GENERATED == "signal_generated"

    def test_all_members_present(self):
        names = {et.name for et in EventType}
        assert {
            "SIGNAL_GENERATED",
            "ORDER_PLACED",
            "ORDER_FILLED",
            "ORDER_CANCELLED",
            "POSITION_OPENED",
            "POSITION_CLOSED",
            "RISK_ALERT",
        }.issubset(names)


class TestEventBusSubscription:
    def test_subscribe_adds_handler(self):
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe(EventType.SIGNAL_GENERATED, handler)
        assert handler in bus.listeners[EventType.SIGNAL_GENERATED]

    def test_unsubscribe_removes_handler(self):
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe(EventType.SIGNAL_GENERATED, handler)
        bus.unsubscribe(EventType.SIGNAL_GENERATED, handler)
        assert handler not in bus.listeners.get(EventType.SIGNAL_GENERATED, [])

    def test_multiple_subscribers_same_event(self):
        bus = EventBus()
        h1, h2 = MagicMock(), MagicMock()
        bus.subscribe(EventType.ORDER_PLACED, h1)
        bus.subscribe(EventType.ORDER_PLACED, h2)
        assert len(bus.listeners[EventType.ORDER_PLACED]) == 2


class TestLocalHandlerRouting:
    async def test_sync_handler_called(self):
        bus = EventBus()
        called = []
        bus.subscribe(EventType.SIGNAL_GENERATED, lambda e: called.append(e))
        await bus._trigger_local_handlers(_make_event())
        assert len(called) == 1

    async def test_async_handler_called(self):
        bus = EventBus()
        handler = AsyncMock()
        bus.subscribe(EventType.SIGNAL_GENERATED, handler)
        event = _make_event()
        await bus._trigger_local_handlers(event)
        handler.assert_awaited_once_with(event)

    async def test_handler_exception_does_not_propagate(self):
        bus = EventBus()

        def bad(_event):
            raise RuntimeError("boom")

        good_called = []
        bus.subscribe(EventType.SIGNAL_GENERATED, bad)
        bus.subscribe(EventType.SIGNAL_GENERATED, lambda e: good_called.append(e))
        # Must not raise and must still call the good handler
        await bus._trigger_local_handlers(_make_event())
        assert len(good_called) == 1

    async def test_no_handlers_no_op(self):
        bus = EventBus()
        await bus._trigger_local_handlers(_make_event(EventType.POSITION_OPENED))

    async def test_only_matching_type_invoked(self):
        bus = EventBus()
        a_called, b_called = [], []
        bus.subscribe(EventType.SIGNAL_GENERATED, lambda e: a_called.append(e))
        bus.subscribe(EventType.ORDER_PLACED, lambda e: b_called.append(e))
        await bus._trigger_local_handlers(_make_event(EventType.SIGNAL_GENERATED))
        assert len(a_called) == 1
        assert len(b_called) == 0


class TestRunningState:
    def test_default_not_running(self):
        bus = EventBus()
        assert bus.running is False

    async def test_stop_listening_clears_flag(self):
        bus = EventBus()
        bus.running = True
        await bus.stop_listening()
        assert bus.running is False
