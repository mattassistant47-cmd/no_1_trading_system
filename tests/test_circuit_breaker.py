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

    def test_all_reasons(self):
        names = {r.name for r in TriggerReason}
        assert {
            "MAX_DAILY_LOSS",
            "MAX_DRAWDOWN",
            "VOLATILITY_SPIKE",
            "SYSTEM_ERROR",
            "HEARTBEAT_FAILURE",
            "CORRELATION_BREAKDOWN",
            "LIQUIDITY_CRISIS",
            "MANUAL_TRIGGER",
        }.issubset(names)


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

    async def test_manual_trigger_custom_reason_captured(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("circuit test XYZ")
        assert "XYZ" in cb.events[0].message


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

    async def test_recovery_when_not_triggered_returns_true(self):
        cb = CircuitBreaker()
        recovered = await cb.attempt_recovery()
        assert recovered is True

    async def test_recovery_marks_event_resolved(self):
        cb = CircuitBreaker(cooldown_minutes=0)
        await cb.manual_trigger("test")
        cb.trigger_time = datetime.utcnow() - timedelta(minutes=5)
        await cb.attempt_recovery()
        assert cb.events[-1].resolved is True
        assert cb.events[-1].recovery_time is not None


class TestReset:
    async def test_manual_reset(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("test")
        assert cb.is_triggered is True
        await cb.reset()
        assert cb.is_triggered is False
        assert cb.state == CircuitState.NORMAL
        assert cb.trigger_time is None

    async def test_reset_and_trigger_again(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("first")
        await cb.reset()
        await cb.manual_trigger("second")
        assert cb.is_triggered is True
        assert cb.state == CircuitState.HALTED
        assert len(cb.events) == 2


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

    def test_warning_multiplier(self):
        cb = CircuitBreaker()
        cb.state = CircuitState.WARNING
        assert cb.get_position_size_multiplier() == 0.75

    def test_reduced_multiplier(self):
        cb = CircuitBreaker()
        cb.state = CircuitState.REDUCED
        assert cb.get_position_size_multiplier() == 0.5

    def test_liquidating_multiplier(self):
        cb = CircuitBreaker()
        cb.state = CircuitState.LIQUIDATING
        assert cb.get_position_size_multiplier() == 0.0


class TestGetStatus:
    def test_status_dict(self):
        cb = CircuitBreaker()
        s = cb.get_status()
        assert s["state"] == "normal"
        assert s["is_triggered"] is False
        assert s["trigger_time"] is None
        assert "last_heartbeat" in s

    async def test_status_after_trigger(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("x")
        s = cb.get_status()
        assert s["is_triggered"] is True
        assert s["trigger_time"] is not None


class TestEventHistory:
    async def test_event_logged(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("test event")
        history = cb.get_event_history()
        assert len(history) == 1
        assert history[0]["reason"] == "manual_trigger"
        assert history[0]["resolved"] is False

    async def test_event_history_limit(self):
        cb = CircuitBreaker()
        await cb.manual_trigger("first")
        await cb.reset()
        await cb.manual_trigger("second")
        await cb.reset()
        await cb.manual_trigger("third")
        history = cb.get_event_history(limit=2)
        assert len(history) == 2


class TestLiquidateAll:
    async def test_liquidation_state(self):
        cb = CircuitBreaker()
        await cb.liquidate_all()
        assert cb.state == CircuitState.LIQUIDATING

    async def test_liquidation_callback_invoked(self):
        called = []

        async def on_liq():
            called.append(True)

        cb = CircuitBreaker()
        cb.on_liquidating = on_liq
        await cb.liquidate_all()
        assert len(called) == 1


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

    async def test_sync_callback_invoked(self):
        called = []

        def on_halt_sync():
            called.append(True)

        cb = CircuitBreaker()
        cb.on_halted = on_halt_sync
        await cb.manual_trigger("test")
        assert len(called) == 1

    async def test_callback_exception_swallowed(self):
        async def bad_callback():
            raise RuntimeError("boom")

        cb = CircuitBreaker()
        cb.on_halted = bad_callback
        # Should not raise
        await cb.manual_trigger("test")
        assert cb.is_triggered is True


class TestIdempotentTrigger:
    async def test_double_trigger_only_one_event(self):
        cb = CircuitBreaker()
        await cb.check_daily_loss(5.0)
        await cb.check_drawdown(15.0)
        assert len(cb.events) == 1


class TestLiquidityCrisis:
    async def test_within_spread_no_trigger(self):
        cb = CircuitBreaker()
        triggered = await cb.check_liquidity_crisis(0.1, spread_threshold_pct=1.0)
        assert triggered is False

    async def test_wide_spread_triggers(self):
        cb = CircuitBreaker()
        triggered = await cb.check_liquidity_crisis(5.0, spread_threshold_pct=1.0)
        assert triggered is True


class TestCorrelationBreakdown:
    async def test_healthy_correlation_no_trigger(self):
        cb = CircuitBreaker()
        triggered = await cb.check_correlation_breakdown(0.8)
        assert triggered is False

    async def test_breakdown_triggers(self):
        cb = CircuitBreaker()
        triggered = await cb.check_correlation_breakdown(0.1)
        assert triggered is True
