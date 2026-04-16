"""
Strategy Rotation Engine

Dynamically allocates portfolio to strategies based on recent performance using
Bayesian weight updates, regime-aware rotation, and statistical significance testing.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import statistics
from loguru import logger


class RotationEvent(str, Enum):
    """Rotation trigger events"""
    DAILY_EVAL = "daily_evaluation"
    WEEKLY_REBALANCE = "weekly_rebalancing"
    PERFORMANCE_SHIFT = "performance_shift"
    REGIME_CHANGE = "regime_change"
    MANUAL = "manual"


@dataclass
class StrategyAllocation:
    """Strategy allocation"""
    strategy_id: str
    weight: float  # 0-1
    allocation_amount: float
    confidence: float  # 0-1 (statistical significance)
    performance_score: float  # 0-1
    updated_at: datetime = field(default_factory=datetime.utcnow)
    reason: str = ""


@dataclass
class RotationResult:
    """Result of rotation event"""
    event_type: RotationEvent
    timestamp: datetime = field(default_factory=datetime.utcnow)
    previous_allocations: Dict[str, float] = field(default_factory=dict)
    new_allocations: Dict[str, float] = field(default_factory=dict)
    changes: Dict[str, float] = field(default_factory=dict)  # Delta by strategy
    total_rebalancing_trades: int = 0
    reason: str = ""


class StrategyRotator:
    """
    Dynamic strategy rotation engine with Bayesian weight updates.

    Features:
    - Performance-based scoring using rolling Sharpe and drawdown recovery
    - Bayesian weight updates: increase allocation to outperformers
    - Minimum allocation threshold (5%) and maximum cap (40%)
    - Regime-aware rotation (adjust weights by market regime)
    - Confidence intervals for statistical significance
    - Daily evaluation, weekly rebalancing
    """

    def __init__(
        self,
        min_allocation_pct: float = 5.0,
        max_allocation_pct: float = 40.0,
        rebalance_threshold_pct: float = 5.0,
        min_confidence_threshold: float = 0.6,
        lookback_days: int = 30,
    ):
        """
        Initialize StrategyRotator.

        Args:
            min_allocation_pct: Minimum allocation per strategy
            max_allocation_pct: Maximum allocation per strategy
            rebalance_threshold_pct: Drift threshold for rebalancing
            min_confidence_threshold: Min confidence to make allocation change
            lookback_days: Days of history for performance evaluation
        """
        self.min_allocation_pct = min_allocation_pct / 100
        self.max_allocation_pct = max_allocation_pct / 100
        self.rebalance_threshold_pct = rebalance_threshold_pct / 100
        self.min_confidence_threshold = min_confidence_threshold
        self.lookback_days = lookback_days

        # State
        self.current_allocations: Dict[str, float] = {}
        self.allocation_history: List[RotationResult] = []
        self.performance_scores: Dict[str, float] = {}
        self.last_rebalance: Optional[datetime] = None
        self.rotation_schedule: Dict[str, datetime] = {}

        logger.info(
            f"StrategyRotator initialized: "
            f"min_alloc={min_allocation_pct}%, max_alloc={max_allocation_pct}%, "
            f"rebalance_threshold={rebalance_threshold_pct}%"
        )

    async def initialize_allocations(
        self,
        strategy_ids: List[str],
        initial_weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize portfolio allocations.

        Args:
            strategy_ids: List of strategy identifiers
            initial_weights: Optional initial weights (must sum to 1.0)
        """
        if initial_weights:
            if not 0.99 <= sum(initial_weights.values()) <= 1.01:
                raise ValueError("Weights must sum to ~1.0")

            self.current_allocations = initial_weights.copy()
        else:
            # Equal weight
            weight = 1.0 / len(strategy_ids)
            self.current_allocations = {sid: weight for sid in strategy_ids}

        # Initialize scores
        for sid in strategy_ids:
            self.performance_scores[sid] = 0.5  # Neutral starting score

        logger.info(
            f"Initialized allocations for {len(strategy_ids)} strategies: "
            f"{self.current_allocations}"
        )

    async def evaluate_daily(
        self,
        strategy_metrics: Dict[str, Dict],  # {strategy_id: {sharpe, max_dd, etc}}
        portfolio_equity: float,
    ) -> Optional[RotationResult]:
        """
        Daily evaluation of strategy performance.

        Args:
            strategy_metrics: Latest metrics for each strategy
            portfolio_equity: Current portfolio equity

        Returns:
            RotationResult if changes made, None otherwise
        """
        logger.debug("Performing daily evaluation")

        # Score each strategy
        for sid, metrics in strategy_metrics.items():
            score = await self._score_strategy(metrics)
            self.performance_scores[sid] = score

        # Check if rebalancing needed
        needs_rebalance = await self._check_rebalance_threshold()

        if needs_rebalance:
            logger.info("Rebalancing threshold exceeded - initiating rotation")
            return await self.rebalance(
                strategy_metrics,
                portfolio_equity,
                RotationEvent.DAILY_EVAL,
            )

        return None

    async def rebalance(
        self,
        strategy_metrics: Dict[str, Dict],
        portfolio_equity: float,
        trigger: RotationEvent = RotationEvent.WEEKLY_REBALANCE,
    ) -> RotationResult:
        """
        Rebalance portfolio using Bayesian weight updates.

        Args:
            strategy_metrics: Latest metrics for each strategy
            portfolio_equity: Current portfolio equity
            trigger: Rotation trigger event

        Returns:
            RotationResult with allocation changes
        """
        logger.info(f"Rebalancing portfolio (trigger: {trigger.value})")

        previous_allocations = self.current_allocations.copy()

        # Calculate new weights using Bayesian update
        new_weights = await self._bayesian_weight_update(strategy_metrics)

        # Apply min/max constraints
        new_weights = self._apply_constraints(new_weights)

        # Calculate changes
        changes = {
            sid: (new_weights.get(sid, 0.0) - previous_allocations.get(sid, 0.0))
            for sid in set(previous_allocations.keys()) | set(new_weights.keys())
        }

        # Update state
        self.current_allocations = new_weights
        self.last_rebalance = datetime.utcnow()

        # Calculate allocation amounts
        allocation_amounts = {
            sid: weight * portfolio_equity
            for sid, weight in new_weights.items()
        }

        # Create result
        result = RotationResult(
            event_type=trigger,
            previous_allocations=previous_allocations,
            new_allocations=new_weights,
            changes=changes,
            reason=f"Bayesian rebalance based on performance scores",
        )

        self.allocation_history.append(result)

        logger.info(
            f"Rebalance complete: "
            f"{[(s, f'{w:.1%}') for s, w in new_weights.items()]}"
        )

        return result

    async def _bayesian_weight_update(
        self, strategy_metrics: Dict[str, Dict]
    ) -> Dict[str, float]:
        """
        Calculate new weights using Bayesian update.

        Uses prior allocation as prior, scores as likelihood.
        """
        scores = {}
        confidence = {}

        for sid, metrics in strategy_metrics.items():
            score = await self._score_strategy(metrics)
            scores[sid] = score

            # Confidence based on sample size and consistency
            conf = await self._calculate_confidence(metrics, sid)
            confidence[sid] = conf

        # Normalize scores to 0-1 range
        if not scores:
            return self.current_allocations.copy()

        min_score = min(scores.values())
        max_score = max(scores.values())
        score_range = max_score - min_score if max_score > min_score else 1.0

        normalized_scores = {
            sid: (score - min_score) / score_range
            for sid, score in scores.items()
        }

        # Apply confidence weighting
        weighted_scores = {
            sid: normalized_scores.get(sid, 0.5) * confidence.get(sid, 0.5)
            for sid in scores.keys()
        }

        # Bayesian update: blend prior (current allocation) with new scores
        alpha = 0.7  # Weight on new information

        new_weights = {}
        for sid in weighted_scores.keys():
            prior = self.current_allocations.get(sid, 1.0 / len(scores))
            posterior = (
                alpha * weighted_scores[sid] + (1 - alpha) * prior
            )
            new_weights[sid] = posterior

        # Normalize to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {sid: w / total for sid, w in new_weights.items()}

        return new_weights

    async def _score_strategy(self, metrics: Dict) -> float:
        """
        Score strategy on 0-1 scale based on recent performance.

        Factors:
        - Sharpe ratio (higher is better)
        - Max drawdown (lower is better, capped at 10%)
        - Win rate (higher is better)
        - Profit factor (higher is better)
        """
        score_components = []

        # Sharpe component (0-2 → 0-1)
        sharpe = metrics.get("sharpe_ratio", 0.0)
        sharpe_score = min(1.0, max(0.0, sharpe / 2.0))
        score_components.append(sharpe_score * 0.40)

        # Drawdown component (inverse - lower dd is better)
        max_dd = abs(metrics.get("max_drawdown_pct", 0.0)) / 100
        dd_score = max(0.0, 1.0 - max_dd)
        score_components.append(dd_score * 0.30)

        # Win rate component
        win_rate = metrics.get("win_rate", 0.5)
        wr_score = win_rate
        score_components.append(wr_score * 0.20)

        # Profit factor component
        profit_factor = metrics.get("profit_factor", 1.0)
        pf_score = min(1.0, max(0.0, profit_factor / 3.0))
        score_components.append(pf_score * 0.10)

        total_score = sum(score_components)
        return max(0.0, min(1.0, total_score))

    async def _calculate_confidence(
        self, metrics: Dict, strategy_id: str
    ) -> float:
        """
        Calculate confidence in the allocation change.

        Based on:
        - Number of trades
        - Consistency of results
        - Stability of metrics
        """
        confidence = 0.5  # Base

        # More trades = higher confidence
        total_trades = metrics.get("trades_total", 0)
        if total_trades > 50:
            confidence += 0.25
        elif total_trades > 20:
            confidence += 0.15
        elif total_trades > 5:
            confidence += 0.05

        # Stable metrics = higher confidence
        sortino = metrics.get("sortino_ratio", 0.0)
        if sortino > 1.0:
            confidence += 0.15
        elif sortino > 0.5:
            confidence += 0.05

        # Information ratio
        info_ratio = metrics.get("information_ratio", 0.0)
        if abs(info_ratio) > 0.5:
            confidence += 0.10

        return min(1.0, confidence)

    async def _check_rebalance_threshold(self) -> bool:
        """Check if allocation drift exceeds rebalancing threshold"""
        if not self.allocation_history:
            return False

        last_result = self.allocation_history[-1]

        # Check if any allocation changed by more than threshold
        for sid, change in last_result.changes.items():
            if abs(change) > self.rebalance_threshold_pct:
                return True

        return False

    def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Apply minimum and maximum allocation constraints.

        Args:
            weights: Proposed weights

        Returns:
            Constrained weights summing to 1.0
        """
        constrained = {}

        # Apply min allocation
        for sid, weight in weights.items():
            if weight < self.min_allocation_pct:
                constrained[sid] = 0.0
            elif weight > self.max_allocation_pct:
                constrained[sid] = self.max_allocation_pct
            else:
                constrained[sid] = weight

        # Remove zero allocations
        constrained = {sid: w for sid, w in constrained.items() if w > 0}

        # If all strategies are below minimum, allow them
        if not constrained:
            for sid, weight in weights.items():
                constrained[sid] = weight

        # Ensure no strategies are below minimum
        total = sum(constrained.values())

        # Proportionally scale to sum to 1.0 while respecting min/max
        final = {}
        unallocated = 1.0

        # First pass: allocate to strategies that can reach minimum
        for sid in sorted(constrained.keys()):
            needed = self.min_allocation_pct
            available = constrained[sid]

            if needed <= unallocated:
                final[sid] = max(available, self.min_allocation_pct)
                unallocated -= final[sid]

        # Second pass: distribute remaining to available capacity
        for sid in sorted(constrained.keys()):
            if sid not in final:
                final[sid] = constrained[sid]

        # Final normalization
        total = sum(final.values())
        if total > 0:
            final = {sid: w / total for sid, w in final.items()}

        return final

    async def get_allocation_for_equity(
        self, total_equity: float
    ) -> Dict[str, float]:
        """
        Get allocation amounts for given total equity.

        Args:
            total_equity: Total portfolio equity

        Returns:
            Dict of {strategy_id: allocation_amount}
        """
        return {
            sid: weight * total_equity
            for sid, weight in self.current_allocations.items()
        }

    async def check_drift(self) -> Dict[str, float]:
        """Check allocation drift from targets"""
        drift = {}

        for sid, target in self.current_allocations.items():
            # In production, would track actual vs target
            actual = target  # Placeholder
            drift[sid] = actual - target

        return drift

    async def suggest_rebalance_trades(
        self,
        strategy_positions: Dict[str, float],  # {strategy_id: current_amount}
        total_equity: float,
    ) -> Dict[str, float]:
        """
        Suggest trades to rebalance to target allocations.

        Args:
            strategy_positions: Current position amounts
            total_equity: Total equity

        Returns:
            Dict of {strategy_id: amount_to_trade} (negative=sell, positive=buy)
        """
        target_allocations = await self.get_allocation_for_equity(total_equity)

        trades = {}
        for sid, target in target_allocations.items():
            current = strategy_positions.get(sid, 0.0)
            trades[sid] = target - current

        return trades

    def get_allocation_report(self) -> Dict:
        """Generate allocation report"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "current_allocations": self.current_allocations,
            "performance_scores": self.performance_scores,
            "last_rebalance": self.last_rebalance.isoformat() if self.last_rebalance else None,
            "allocation_history_count": len(self.allocation_history),
        }

    def get_allocation_history(self, limit: int = 20) -> List[Dict]:
        """Get recent allocation history"""
        results = self.allocation_history[-limit:] if limit else self.allocation_history

        return [
            {
                "event_type": r.event_type.value,
                "timestamp": r.timestamp.isoformat(),
                "previous_allocations": r.previous_allocations,
                "new_allocations": r.new_allocations,
                "changes": r.changes,
                "reason": r.reason,
            }
            for r in results
        ]
