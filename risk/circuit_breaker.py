"""
Emergency Stop / Circuit Breaker System

Monitors system health and trading metrics with graduated response:
warning → reduce exposure → halt trading → close all positions.
Includes dead man's switch for system failures.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable, Dict, List
from loguru import logger


class CircuitState(str, Enum):
    """Circuit breaker states"""
    NORMAL = "normal"
    WARNING = "warning"
    REDUCED = "reduced"
    HALTED = "halted"
    LIQUIDATING = "liquidating"


class TriggerReason(str, Enum):
    """Circuit breaker trigger reasons"""
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    VOLATILITY_SPIKE = "volatility_spike"
    SYSTEM_ERROR = "system_error"
    HEARTBEAT_FAILURE = "heartbeat_failure"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    MANUAL_TRIGGER = "manual_trigger"


@dataclass
class CircuitEvent:
    """Circuit breaker event"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    state: CircuitState = CircuitState.NORMAL
    reason: Optional[TriggerReason] = None
    message: str = ""
    severity: int = 0  # 0=info, 1=warning, 2=error, 3=critical
    resolved: bool = False
    recovery_time: Optional[datetime] = None


class CircuitBreaker:
    """
    Emergency stop system with graduated response and dead man's switch.

    Triggers on:
    - Max daily loss exceeded
    - Max drawdown exceeded
    - Volatility spike (3-sigma event)
    - System errors
    - Missing heartbeat (>5 minutes)
    - Correlation breakdown
    - Liquidity crisis

    Response gradient:
    1. WARNING: Log alert, notify user
    2. REDUCED: Cut position size by 50%, disable new trades
    3. HALTED: Cancel all pending orders
    4. LIQUIDATING: Force close all positions
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 2.0,
        max_drawdown_pct: float = 10.0,
        volatility_threshold: float = 3.0,  # Standard deviations
        heartbeat_timeout_sec: int = 300,  # 5 minutes
        cooldown_minutes: int = 60,
        auto_recovery: bool = True,
    ):
        """
        Initialize CircuitBreaker.

        Args:
            max_daily_loss_pct: Max daily loss before trigger
            max_drawdown_pct: Max drawdown before trigger
            volatility_threshold: Volatility spike threshold (std devs)
            heartbeat_timeout_sec: Heartbeat timeout in seconds
            cooldown_minutes: Cooldown before auto-recovery
            auto_recovery: Enable automatic recovery
        """
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.volatility_threshold = volatility_threshold
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.cooldown_minutes = cooldown_minutes
        self.auto_recovery = auto_recovery

        # State
        self.state = CircuitState.NORMAL
        self.is_triggered = False
        self.trigger_time: Optional[datetime] = None
        self.last_heartbeat = datetime.utcnow()
        self.events: List[CircuitEvent] = []

        # Callbacks
        self.on_warning: Optional[Callable] = None
        self.on_reduced: Optional[Callable] = None
        self.on_halted: Optional[Callable] = None
        self.on_liquidating: Optional[Callable] = None
        self.on_recovery: Optional[Callable] = None

        # Metrics
        self.volatility_samples: List[float] = []
        self.max_volatility_samples = 100

        logger.info(
            f"CircuitBreaker initialized: "
            f"max_daily_loss={max_daily_loss_pct}%, "
            f"max_drawdown={max_drawdown_pct}%, "
            f"heartbeat_timeout={heartbeat_timeout_sec}s"
        )

    async def check_daily_loss(
        self, current_loss_pct: float
    ) -> bool:
        """
        Check if daily loss exceeds limit.

        Args:
            current_loss_pct: Current daily loss as percentage

        Returns:
            True if triggered
        """
        if current_loss_pct < self.max_daily_loss_pct:
            return False

        logger.critical(f"CIRCUIT BREAKER: Daily loss {current_loss_pct:.2f}% exceeds limit")
        await self._trigger(
            TriggerReason.MAX_DAILY_LOSS,
            f"Daily loss {current_loss_pct:.2f}% exceeds limit ({self.max_daily_loss_pct}%)",
            severity=3,
        )
        return True

    async def check_drawdown(
        self, current_drawdown_pct: float
    ) -> bool:
        """
        Check if drawdown exceeds limit.

        Args:
            current_drawdown_pct: Current drawdown as percentage

        Returns:
            True if triggered
        """
        if current_drawdown_pct < self.max_drawdown_pct:
            return False

        logger.critical(f"CIRCUIT BREAKER: Drawdown {current_drawdown_pct:.2f}% exceeds limit")
        await self._trigger(
            TriggerReason.MAX_DRAWDOWN,
            f"Drawdown {current_drawdown_pct:.2f}% exceeds limit ({self.max_drawdown_pct}%)",
            severity=3,
        )
        return True

    async def check_volatility_spike(
        self, current_volatility: float, mean_volatility: float
    ) -> bool:
        """
        Check for volatility spike (3-sigma event).

        Args:
            current_volatility: Current volatility
            mean_volatility: Mean volatility

        Returns:
            True if triggered
        """
        # Add to sample history
        self.volatility_samples.append(current_volatility)
        if len(self.volatility_samples) > self.max_volatility_samples:
            self.volatility_samples.pop(0)

        # Calculate std dev
        if len(self.volatility_samples) < 20:
            return False

        import statistics
        try:
            std_dev = statistics.stdev(self.volatility_samples)
            z_score = (current_volatility - mean_volatility) / std_dev if std_dev > 0 else 0

            if z_score > self.volatility_threshold:
                logger.critical(
                    f"CIRCUIT BREAKER: Volatility spike detected "
                    f"(z-score: {z_score:.2f})"
                )
                await self._trigger(
                    TriggerReason.VOLATILITY_SPIKE,
                    f"Volatility spike detected (z-score: {z_score:.2f})",
                    severity=2,
                )
                return True
        except Exception as e:
            logger.error(f"Error calculating volatility spike: {e}")

        return False

    async def check_system_error(
        self, error_message: str, critical: bool = False
    ) -> bool:
        """
        Register system error and potentially trigger circuit breaker.

        Args:
            error_message: Error description
            critical: If True, trigger immediately

        Returns:
            True if triggered
        """
        if critical:
            logger.critical(f"CIRCUIT BREAKER: Critical system error: {error_message}")
            await self._trigger(
                TriggerReason.SYSTEM_ERROR,
                f"Critical system error: {error_message}",
                severity=3,
            )
            return True

        logger.error(f"System error: {error_message}")
        return False

    def heartbeat(self):
        """Record heartbeat from main trading loop"""
        self.last_heartbeat = datetime.utcnow()

    async def check_heartbeat(self) -> bool:
        """
        Check if heartbeat is alive (dead man's switch).

        Returns:
            True if triggered
        """
        elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()

        if elapsed > self.heartbeat_timeout_sec:
            logger.critical(
                f"CIRCUIT BREAKER: Heartbeat timeout "
                f"(no pulse for {elapsed:.0f}s)"
            )
            await self._trigger(
                TriggerReason.HEARTBEAT_FAILURE,
                f"Heartbeat timeout: no pulse for {elapsed:.0f}s",
                severity=3,
            )
            return True

        return False

    async def check_correlation_breakdown(
        self, correlation_matrix_health: float
    ) -> bool:
        """
        Check for correlation breakdown (all assets moving together).

        Args:
            correlation_matrix_health: Health score 0-1

        Returns:
            True if triggered
        """
        if correlation_matrix_health < 0.3:
            logger.warning(
                f"CIRCUIT BREAKER: Correlation breakdown "
                f"(health: {correlation_matrix_health:.2f})"
            )
            await self._trigger(
                TriggerReason.CORRELATION_BREAKDOWN,
                f"Correlation breakdown detected (health: {correlation_matrix_health:.2f})",
                severity=2,
            )
            return True

        return False

    async def check_liquidity_crisis(
        self, bid_ask_spread_pct: float, spread_threshold_pct: float = 1.0
    ) -> bool:
        """
        Check for liquidity crisis (abnormal spreads).

        Args:
            bid_ask_spread_pct: Current bid-ask spread %
            spread_threshold_pct: Threshold for alert

        Returns:
            True if triggered
        """
        if bid_ask_spread_pct > spread_threshold_pct:
            logger.warning(
                f"CIRCUIT BREAKER: Liquidity crisis "
                f"(spread: {bid_ask_spread_pct:.2f}%)"
            )
            await self._trigger(
                TriggerReason.LIQUIDITY_CRISIS,
                f"Liquidity crisis: spread {bid_ask_spread_pct:.2f}%",
                severity=2,
            )
            return True

        return False

    async def manual_trigger(self, reason: str = "Manual trigger"):
        """Manually trigger circuit breaker"""
        logger.critical(f"CIRCUIT BREAKER: Manual trigger - {reason}")
        await self._trigger(
            TriggerReason.MANUAL_TRIGGER,
            reason,
            severity=3,
        )

    async def _trigger(
        self,
        reason: TriggerReason,
        message: str,
        severity: int = 2,
    ):
        """
        Internal trigger handler with graduated response.

        Args:
            reason: Trigger reason
            message: Detailed message
            severity: Severity level (0-3)
        """
        if self.is_triggered:
            return  # Already triggered

        self.is_triggered = True
        self.trigger_time = datetime.utcnow()

        # Log event
        event = CircuitEvent(
            state=CircuitState.WARNING,
            reason=reason,
            message=message,
            severity=severity,
        )
        self.events.append(event)

        logger.critical(f"Circuit breaker triggered: {reason.value} - {message}")

        # Graduated response based on severity
        if severity == 1:
            await self._warning_state()
        elif severity == 2:
            await self._reduced_state()
        elif severity == 3:
            await self._halted_state()

    async def _warning_state(self):
        """WARNING state: Log alert, notify user"""
        self.state = CircuitState.WARNING
        logger.warning("Circuit breaker in WARNING state")

        if self.on_warning:
            await self._safe_call(self.on_warning)

    async def _reduced_state(self):
        """REDUCED state: Cut position size, disable new trades"""
        self.state = CircuitState.REDUCED
        logger.error("Circuit breaker in REDUCED state - cutting position sizes")

        if self.on_reduced:
            await self._safe_call(self.on_reduced)

    async def _halted_state(self):
        """HALTED state: Cancel all pending orders"""
        self.state = CircuitState.HALTED
        logger.critical("Circuit breaker in HALTED state - canceling all orders")

        if self.on_halted:
            await self._safe_call(self.on_halted)

    async def liquidate_all(self):
        """Force liquidate all positions"""
        self.state = CircuitState.LIQUIDATING
        logger.critical("Circuit breaker forcing full liquidation")

        if self.on_liquidating:
            await self._safe_call(self.on_liquidating)

    async def attempt_recovery(self) -> bool:
        """
        Attempt to recover from triggered state.

        Returns:
            True if recovery successful
        """
        if not self.is_triggered or self.trigger_time is None:
            return True

        # Check cooldown period
        elapsed = (datetime.utcnow() - self.trigger_time).total_seconds()
        required_cooldown = self.cooldown_minutes * 60

        if elapsed < required_cooldown:
            logger.info(
                f"Circuit breaker cooldown active "
                f"({elapsed:.0f}s / {required_cooldown:.0f}s)"
            )
            return False

        if not self.auto_recovery:
            logger.info("Auto-recovery disabled - waiting for manual intervention")
            return False

        # Attempt recovery
        logger.info("Circuit breaker attempting recovery")
        self.is_triggered = False
        self.state = CircuitState.NORMAL

        # Mark event as resolved
        if self.events:
            self.events[-1].resolved = True
            self.events[-1].recovery_time = datetime.utcnow()

        if self.on_recovery:
            await self._safe_call(self.on_recovery)

        logger.info("Circuit breaker recovered to NORMAL state")
        return True

    async def reset(self):
        """Manually reset circuit breaker"""
        logger.warning("Circuit breaker manually reset")
        self.is_triggered = False
        self.state = CircuitState.NORMAL
        self.trigger_time = None

    def get_status(self) -> Dict:
        """Get circuit breaker status"""
        time_since_trigger = None
        if self.trigger_time:
            time_since_trigger = (datetime.utcnow() - self.trigger_time).total_seconds()

        time_since_heartbeat = (datetime.utcnow() - self.last_heartbeat).total_seconds()

        return {
            "state": self.state.value,
            "is_triggered": self.is_triggered,
            "trigger_time": self.trigger_time.isoformat() if self.trigger_time else None,
            "time_since_trigger_sec": time_since_trigger,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "time_since_heartbeat_sec": time_since_heartbeat,
            "last_event": self.events[-1] if self.events else None,
            "total_events": len(self.events),
        }

    async def _safe_call(self, callback: Callable) -> None:
        """Safely call callback with error handling"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback()
            else:
                callback()
        except Exception as e:
            logger.error(f"Error in circuit breaker callback: {e}")

    def get_event_history(self, limit: int = 100) -> List[Dict]:
        """Get event history"""
        events = self.events[-limit:] if limit else self.events
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "state": e.state.value,
                "reason": e.reason.value if e.reason else None,
                "message": e.message,
                "severity": e.severity,
                "resolved": e.resolved,
                "recovery_time": e.recovery_time.isoformat() if e.recovery_time else None,
            }
            for e in events
        ]

    def can_trade(self) -> bool:
        """Check if trading is allowed"""
        return self.state in (CircuitState.NORMAL, CircuitState.WARNING)

    def can_open_new_positions(self) -> bool:
        """Check if new positions can be opened"""
        return self.state == CircuitState.NORMAL

    def get_position_size_multiplier(self) -> float:
        """Get position size multiplier based on state"""
        multipliers = {
            CircuitState.NORMAL: 1.0,
            CircuitState.WARNING: 0.75,
            CircuitState.REDUCED: 0.5,
            CircuitState.HALTED: 0.0,
            CircuitState.LIQUIDATING: 0.0,
        }
        return multipliers.get(self.state, 0.0)


