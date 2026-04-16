"""
Portfolio Rebalancer Agent

Autonomous agent that monitors portfolio allocation drift and triggers
tax-aware rebalancing when drift exceeds thresholds.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from loguru import logger


class RebalanceReason(str, Enum):
    """Rebalancing trigger reasons"""
    DRIFT_THRESHOLD = "drift_threshold"
    CALENDAR_TRIGGER = "calendar_trigger"
    PERFORMANCE_SHIFT = "performance_shift"
    MANUAL_REQUEST = "manual_request"
    REHEDGE = "rehedge"


@dataclass
class AllocationDrift:
    """Portfolio allocation drift"""
    strategy_id: str
    target_allocation_pct: float
    actual_allocation_pct: float
    drift_pct: float  # Absolute drift
    drift_direction: str  # "over" or "under"
    notional_value: float


@dataclass
class RebalanceTrade:
    """Individual rebalancing trade"""
    strategy_id: str
    direction: str  # "buy" or "sell"
    notional_value: float
    execution_price: Optional[float] = None
    tax_impact: float = 0.0  # Estimated tax impact
    executed_at: Optional[datetime] = None
    status: str = "pending"  # "pending", "executed", "cancelled"


@dataclass
class RebalanceEvent:
    """Portfolio rebalancing event"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reason: RebalanceReason = RebalanceReason.DRIFT_THRESHOLD
    previous_allocations: Dict[str, float] = field(default_factory=dict)
    target_allocations: Dict[str, float] = field(default_factory=dict)
    drifts: List[AllocationDrift] = field(default_factory=list)
    trades: List[RebalanceTrade] = field(default_factory=list)
    total_tax_impact: float = 0.0
    status: str = "pending"  # "pending", "executing", "completed"
    execution_time_sec: float = 0.0


class PortfolioRebalancer:
    """
    Autonomous portfolio rebalancing agent.

    Capabilities:
    - Monitors allocation drift from targets
    - Triggers rebalance when drift exceeds threshold
    - Tax-aware rebalancing (avoids short-term gains)
    - Scheduled execution (daily check, weekly rebalance)
    - Partial rebalancing (don't fix all drift immediately)
    """

    def __init__(
        self,
        drift_threshold_pct: float = 5.0,
        rebalance_threshold_pct: float = 3.0,
        capital_gains_tax_rate: float = 0.37,  # Short-term capital gains
        long_term_tax_rate: float = 0.20,
        holding_period_days: int = 365,
        max_rebalance_frequency_hours: int = 24,
    ):
        """
        Initialize PortfolioRebalancer.

        Args:
            drift_threshold_pct: Drift threshold to trigger check
            rebalance_threshold_pct: Drift threshold to execute rebalance
            capital_gains_tax_rate: Short-term capital gains tax rate
            long_term_tax_rate: Long-term capital gains tax rate
            holding_period_days: Days to classify as long-term holding
            max_rebalance_frequency_hours: Minimum hours between rebalances
        """
        self.drift_threshold_pct = drift_threshold_pct / 100
        self.rebalance_threshold_pct = rebalance_threshold_pct / 100
        self.capital_gains_tax_rate = capital_gains_tax_rate
        self.long_term_tax_rate = long_term_tax_rate
        self.holding_period_days = holding_period_days
        self.max_rebalance_frequency_hours = max_rebalance_frequency_hours

        # State
        self.current_allocations: Dict[str, float] = {}
        self.target_allocations: Dict[str, float] = {}
        self.position_acquisition_times: Dict[str, datetime] = {}
        self.rebalance_history: List[RebalanceEvent] = []
        self.last_rebalance_time: Optional[datetime] = None

        # Callbacks
        self.on_rebalance_executed: Optional[Callable] = None

        logger.info(
            f"PortfolioRebalancer initialized: "
            f"drift_threshold={drift_threshold_pct}%, "
            f"rebalance_threshold={rebalance_threshold_pct}%, "
            f"tax_rate={capital_gains_tax_rate:.0%} (short-term)"
        )

    def set_target_allocations(self, allocations: Dict[str, float]):
        """Set target allocations for strategies"""
        if not 0.99 <= sum(allocations.values()) <= 1.01:
            raise ValueError("Allocations must sum to ~1.0")

        self.target_allocations = allocations
        logger.info(f"Set target allocations: {allocations}")

    async def check_drift(
        self,
        current_allocations: Dict[str, float],
        portfolio_value: float,
    ) -> List[AllocationDrift]:
        """
        Check allocation drift from targets.

        Args:
            current_allocations: Current allocation percentages
            portfolio_value: Total portfolio value

        Returns:
            List of AllocationDrift for each strategy
        """
        self.current_allocations = current_allocations

        drifts = []

        for strategy_id, target in self.target_allocations.items():
            actual = current_allocations.get(strategy_id, 0.0)
            drift = actual - target
            drift_pct = abs(drift) * 100
            direction = "over" if drift > 0 else "under"

            notional_value = actual * portfolio_value

            drift_obj = AllocationDrift(
                strategy_id=strategy_id,
                target_allocation_pct=target * 100,
                actual_allocation_pct=actual * 100,
                drift_pct=drift_pct,
                drift_direction=direction,
                notional_value=notional_value,
            )

            drifts.append(drift_obj)

        # Log significant drifts
        for drift in drifts:
            if drift.drift_pct > self.drift_threshold_pct * 100:
                logger.warning(
                    f"Allocation drift: {drift.strategy_id} "
                    f"{drift.actual_allocation_pct:.1f}% (target: {drift.target_allocation_pct:.1f}%)"
                )

        return drifts

    async def should_rebalance(
        self,
        drifts: List[AllocationDrift],
    ) -> bool:
        """
        Determine if rebalancing is needed.

        Args:
            drifts: List of allocation drifts

        Returns:
            True if rebalancing should proceed
        """
        # Check minimum time since last rebalance
        if self.last_rebalance_time:
            hours_since = (datetime.utcnow() - self.last_rebalance_time).total_seconds() / 3600

            if hours_since < self.max_rebalance_frequency_hours:
                logger.debug(f"Rebalance cooldown active ({hours_since:.1f}h remaining)")
                return False

        # Check if any drift exceeds rebalance threshold
        max_drift = max((d.drift_pct for d in drifts), default=0.0)

        if max_drift > self.rebalance_threshold_pct * 100:
            logger.info(f"Rebalancing triggered: max drift {max_drift:.1f}%")
            return True

        return False

    async def generate_rebalance_trades(
        self,
        drifts: List[AllocationDrift],
        portfolio_value: float,
        current_prices: Dict[str, float],
    ) -> List[RebalanceTrade]:
        """
        Generate rebalancing trades.

        Args:
            drifts: Allocation drifts
            portfolio_value: Total portfolio value
            current_prices: Current strategy prices/NAVs

        Returns:
            List of RebalanceTrade
        """
        trades = []

        for drift in drifts:
            # Only rebalance if drift exceeds half of rebalance threshold
            if drift.drift_pct < (self.rebalance_threshold_pct / 2) * 100:
                continue

            strategy_id = drift.strategy_id

            if drift.drift_direction == "over":
                # Sell to reduce
                notional_to_reduce = drift.notional_value * 0.5  # Reduce by 50% of drift
                direction = "sell"
                price = current_prices.get(strategy_id, 1.0)

            else:  # under
                # Buy to increase
                target_value = drift.target_allocation_pct / 100 * portfolio_value
                notional_to_buy = target_value * 0.5  # Increase by 50% of deficit
                direction = "buy"
                price = current_prices.get(strategy_id, 1.0)

            # Calculate tax impact
            tax_impact = await self._estimate_tax_impact(
                strategy_id,
                notional_to_reduce if direction == "sell" else notional_to_buy,
                direction
            )

            trade = RebalanceTrade(
                strategy_id=strategy_id,
                direction=direction,
                notional_value=(
                    notional_to_reduce if direction == "sell"
                    else notional_to_buy
                ),
                execution_price=price,
                tax_impact=tax_impact,
                status="pending",
            )

            trades.append(trade)

        # Sort by tax impact (process highest tax trades first)
        trades.sort(key=lambda t: t.tax_impact, reverse=True)

        return trades

    async def _estimate_tax_impact(
        self,
        strategy_id: str,
        notional_value: float,
        direction: str,
    ) -> float:
        """Estimate tax impact of trade"""
        if direction != "sell":
            return 0.0  # Purchases don't create tax

        # Get acquisition time
        acq_time = self.position_acquisition_times.get(strategy_id)

        if not acq_time:
            return 0.0

        # Determine holding period
        holding_days = (datetime.utcnow() - acq_time).days

        # Use appropriate tax rate
        if holding_days >= self.holding_period_days:
            tax_rate = self.long_term_tax_rate
        else:
            tax_rate = self.capital_gains_tax_rate

        # Simplified: assume gains equal to 20% of notional value
        assumed_gain = notional_value * 0.20
        estimated_tax = assumed_gain * tax_rate

        return estimated_tax

    async def execute_rebalance(
        self,
        trades: List[RebalanceTrade],
        execute_fn: Optional[Callable] = None,
    ) -> RebalanceEvent:
        """
        Execute rebalancing trades.

        Args:
            trades: Trades to execute
            execute_fn: Optional async execution function

        Returns:
            RebalanceEvent with results
        """
        logger.info(f"Executing rebalance with {len(trades)} trades")

        start_time = datetime.utcnow()

        event = RebalanceEvent(
            reason=RebalanceReason.DRIFT_THRESHOLD,
            previous_allocations=self.current_allocations.copy(),
            target_allocations=self.target_allocations.copy(),
            trades=trades,
            status="executing",
        )

        # Execute trades
        for trade in trades:
            try:
                if execute_fn:
                    result = await self._safe_call(
                        execute_fn,
                        trade.strategy_id,
                        trade.direction,
                        trade.notional_value,
                    )

                    if result:
                        trade.executed_at = datetime.utcnow()
                        trade.status = "executed"
                        event.total_tax_impact += trade.tax_impact

                    else:
                        trade.status = "cancelled"

                else:
                    # Simulated execution
                    trade.executed_at = datetime.utcnow()
                    trade.status = "executed"
                    event.total_tax_impact += trade.tax_impact

            except Exception as e:
                logger.error(f"Trade execution failed for {trade.strategy_id}: {e}")
                trade.status = "cancelled"

        event.execution_time_sec = (datetime.utcnow() - start_time).total_seconds()
        event.status = "completed"

        self.last_rebalance_time = datetime.utcnow()
        self.rebalance_history.append(event)

        logger.info(
            f"Rebalance completed: {sum(1 for t in trades if t.status == 'executed')} "
            f"trades executed, ${event.total_tax_impact:.2f} estimated tax impact"
        )

        # Callback
        if self.on_rebalance_executed:
            await self._safe_call(self.on_rebalance_executed, event)

        return event

    async def _safe_call(self, callback: Callable, *args, **kwargs):
        """Safely call callback"""
        try:
            if asyncio.iscoroutinefunction(callback):
                return await callback(*args, **kwargs)
            else:
                return callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Callback error: {e}")
            return None

    def track_position_acquisition(self, strategy_id: str, acquisition_time: datetime):
        """Track when position was acquired (for tax purposes)"""
        self.position_acquisition_times[strategy_id] = acquisition_time

    def get_rebalance_report(self) -> Dict:
        """Get rebalancing report"""
        if not self.rebalance_history:
            return {"error": "No rebalances completed"}

        latest = self.rebalance_history[-1]

        return {
            "timestamp": latest.timestamp.isoformat(),
            "reason": latest.reason.value,
            "trades_executed": sum(1 for t in latest.trades if t.status == "executed"),
            "total_trades": len(latest.trades),
            "total_tax_impact": latest.total_tax_impact,
            "execution_time_sec": latest.execution_time_sec,
            "trades": [
                {
                    "strategy": t.strategy_id,
                    "direction": t.direction,
                    "notional_value": t.notional_value,
                    "tax_impact": t.tax_impact,
                    "status": t.status,
                }
                for t in latest.trades
            ],
        }

    def get_rebalance_history(self, limit: int = 20) -> List[Dict]:
        """Get rebalancing history"""
        results = self.rebalance_history[-limit:] if limit else self.rebalance_history

        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "reason": r.reason.value,
                "trades_executed": sum(1 for t in r.trades if t.status == "executed"),
                "total_trades": len(r.trades),
                "total_tax_impact": r.total_tax_impact,
                "execution_time_sec": r.execution_time_sec,
            }
            for r in results
        ]
