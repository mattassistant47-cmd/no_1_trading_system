"""Tests for the CircuitBreaker class and its state transitions."""
import pytest
from datetime import datetime, timedelta

from risk.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitEvent,
    TriggerReason,
)


class TestCircuitBreakerInit:
    def test_defaults(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.NORMAL
        assert cb.is_triggered is False
        assert cb.max_daily_loss_pct == 2.0
        assert cb.max_drawdown_pct == 10.0
        assert cb.auto_recovery is True

    def test_custom_params(self):
        cb = CircuitBreaker(max_daily_loss_pct=5.0, cooldown_minutes=30, auto_recovery=False)
        assert cb.max_daily_loss_pct == 5.0
        assert cb.cooldown_minutes == 30
        assert cb.auto_recovery is False


class TestCircuitStateEnum:
    def test_all_states(self):
        assert CircuitState.NORMAL == "normal"
        assert CircuitState.WARNING == "warning"
        assert CircuitState.REDUCED == "reduced"
        assert CircuitState.HALTED == "halted"
        assert CircuitState.LIQUIDATING == "liquidating"


class TestTriggerReasonEnum:
    def test_key_reasons(self):
        assert TriggerReason.MAX_DAILY_LOSS == "max_daily_loss"
        assert TriggerReason.MAX_DRAWDOWN == "max_drawdown"
        assert TriggerReason.SYSTEM_ERROR == "system_error"
        assert TriggerReason.MANUAL_TRIGGER == "manual_trigger"


class TestDailyLossCheck:
    async def test_no_trigger_below_limit(self):
        cb = CircuitBreaker(max_daily_loss_pct=2.0)
        triggered = await cb.check_daily_loss(1.5)
        assert triggered is False
        assert cb.state == CircuitState.NORMAL

    async def test_trigger_at_limit(self):
        cb = CircuitBreaker(max_daily_loss_pct=2.0)
        triggered = await cb.check_daily_loss(2.5)
        assert triggered is True
        assert cb.is_triggered is True
        assert cb.state == CircuitState.HALTED


class TestDrawdownCheck:
    async def test_no_trigger_below_limit(self):
        cb = CircuitBreaker(max_drawdown_pct=10.0)
        triggered = await cb.check_drawdown(5.0)
        assert triggered is False

    async def test_trigger_above_limit(self):
        cb = CircuitBreaker(max_drawdown_pct=10.0)
        triggered = await cb.check_drawdown(12.0)
        assert triggered is True
        assert cb.state == CircuitState.HALTED


class TestSystemErrorCheck:
    async def test_non_critical_no_trigger(self):
        cb = CircuitBreaker()
        triggered = await cb.check_system_error("minor issue", critical=False)
        assert triggered is False
        assert cb.state == CircuitState.NORMAL

    async def test_critical_triggers(self):
        cb = CircuitBreaker()
        triggered = await cb.check_system_error("fatal crash", critical=True)
        assert triggered is True
        assert cb.state == CircuitState.HALTED


class TestHeartbeat:
    def test_heartbeat_updates_timestamp(self):
        cb = CircuitBreaker()
        old_hb = cb.last_heartbeat
        cb.heartbeat()
        assert cb.last_heartbeat >= old_hb

    async def test_heartbeat_alive(self):
        cb = CircuitBreaker(heartbeat_timeout_sec=300)
        cb.heartbeat()
        triggered = await cb.check_heartbeat()
        assert triggered is False

    async def test_heartbeat_timeout(self):
        cb = CircuitBreaker(heartbeat_timeout_sec=1)
        cb.last_heartbeat = datetime.utcnow() - timedelta(seconds=10)
        triggered = await cb.check_heartbeat()
        assert triggered is True
        assert cb.state == CircuitState.HALTED


class TestManualTrigger:
    async def test_manual_trigger(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("operator halt")
        assert cb.is_triggered is True
        assert cb.state == CircuitState.HALTED
        assert len(cb.events) == 1
        assert cb.events[0].reason == TriggerReason.MANUAL_TRIGGER


class TestRecovery:
    async def test_recovery_before_cooldown_fails(self):
        cb = CircuitBreaker(cooldown_minutes=60)
        await cb.manual_trigger("test")
        recovered = await cb.attempt_recovery()
        assert recovered is False
        assert cb.is_triggered is True

    async def test_recovery_after_cooldown(self):
        cb = CircuitBreaker(cooldown_minutes=1)
        await cb.manual_trigger("test")
        cb.trigger_time = datetime.utcnow() - timedelta(minutes=2)
        recovered = await cb.attempt_recovery()
        assert recovered is True
        assert cb.state == CircuitState.NORMAL
        assert cb.is_triggered is False

    async def test_recovery_disabled(self):
        cb = CircuitBreaker(cooldown_minutes=0, auto_recovery=False)
        await cb.manual_trigger("test")
        cb.trigger_time = datetime.utcnow() - timedelta(hours=1)
        recovered = await cb.attempt_recovery()
        assert recovered is False


class TestReset:
    async def test_manual_reset(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("test")
        assert cb.is_triggered is True
        await cb.reset()
        assert cb.is_triggered is False
        assert cb.state == CircuitState.NORMAL
        assert cb.trigger_time is None


class TestCanTrade:
    def test_normal_can_trade(self):
        cb = CircuitBreaker()
        assert cb.can_trade() is True
        assert cb.can_open_new_positions() is True

    async def test_halted_cannot_trade(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("halt")
        assert cb.can_trade() is False
        assert cb.can_open_new_positions() is False


class TestPositionSizeMultiplier:
    def test_normal(self):
        cb = CircuitBreaker()
        assert cb.get_position_size_multiplier() == 1.0

    async def test_halted(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("test")
        assert cb.get_position_size_multiplier() == 0.0


class TestGetStatus:
    def test_status_dict(self):
        cb = CircuitBreaker()
        s = cb.get_status()
        assert s["state"] == "normal"
        assert s["is_triggered"] is False
        assert s["trigger_time"] is None
        assert "last_heartbeat" in s


class TestEventHistory:
    async def test_event_logged(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("test event")
        history = cb.get_event_history()
        assert len(history) == 1
        assert history[0]["reason"] == "manual_trigger"
        assert history[0]["resolved"] is False


class TestLiquidateAll:
    async def test_liquidation_state(self):
        cb = CircuitBreaker()
        await cb.liquidate_all()
        assert cb.state == CircuitState.LIQUIDATING


class TestCallbacks:
    async def test_on_halted_callback(self):
        called = []
        async def on_halt():
            called.append(True)

        cb = CircuitBreaker()
        cb.on_halted = on_halt
        await cb.manual_trigger("test")
        assert len(called) == 1

    async def test_on_recovery_callback(self):
        called = []
        async def on_recover():
            called.append(True)

        cb = CircuitBreaker(cooldown_minutes=0)
        cb.on_recovery = on_recover
        await cb.manual_trigger("test")
        cb.trigger_time = datetime.utcnow() - timedelta(minutes=1)
        await cb.attempt_recovery()
        assert len(called) == 1


class TestIdempotentTrigger:
    async def test_double_trigger_only_one_event(self):
        cb = CircuitBreaker()
        await cb.check_daily_loss(5.0)
        await cb.check_drawdown(15.0)
        assert len(cb.events) == 1
