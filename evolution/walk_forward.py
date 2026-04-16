"""
Walk-Forward Analysis Engine

Sliding window backtest framework with in-sample optimization and out-of-sample
validation. Detects alpha decay and automatically disables underperforming strategies.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable, Any
from enum import Enum
from loguru import logger


class WindowType(str, Enum):
    """Window type for walk-forward analysis"""
    ANCHORED = "anchored"  # Train window grows, test window fixed
    ROLLING = "rolling"    # Both windows slide forward


@dataclass
class WalkForwardWindow:
    """Single walk-forward window"""
    window_number: int
    start_date: datetime
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    in_sample_performance: float = 0.0
    out_of_sample_performance: float = 0.0
    alpha_decay_pct: float = 0.0  # (IS - OOS) / IS
    is_degraded: bool = False


@dataclass
class WalkForwardResult:
    """Walk-forward analysis result"""
    strategy_id: str
    total_windows: int = 0
    average_is_performance: float = 0.0
    average_oos_performance: float = 0.0
    average_alpha_decay_pct: float = 0.0
    worst_oos_window: Optional[WalkForwardWindow] = None
    degradation_detected: bool = False
    windows: List[WalkForwardWindow] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    recommendation: str = ""


class WalkForwardAnalyzer:
    """
    Walk-forward analysis framework for strategy validation.

    Features:
    - Sliding window analysis with in-sample/out-of-sample splits
    - Anchored vs rolling window support
    - Performance degradation detection (out-of-sample alpha decay)
    - Automated strategy disabling when out-of-sample fails
    - Historical result storage and analysis
    """

    def __init__(
        self,
        in_sample_days: int = 90,
        out_of_sample_days: int = 30,
        test_days: Optional[int] = None,
        step_days: int = 10,
        window_type: WindowType = WindowType.ROLLING,
        degradation_threshold_pct: float = 20.0,
        min_windows: int = 4,
    ):
        """
        Initialize WalkForwardAnalyzer.

        Args:
            in_sample_days: In-sample training period
            out_of_sample_days: Out-of-sample testing period
            test_days: Optional independent test period
            step_days: Days to step forward between windows
            window_type: Anchored or rolling windows
            degradation_threshold_pct: Alpha decay threshold to flag degradation
            min_windows: Minimum windows required for analysis
        """
        self.in_sample_days = in_sample_days
        self.out_of_sample_days = out_of_sample_days
        self.test_days = test_days
        self.step_days = step_days
        self.window_type = window_type
        self.degradation_threshold_pct = degradation_threshold_pct
        self.min_windows = min_windows

        # Results storage
        self.results: Dict[str, List[WalkForwardResult]] = {}
        self.disabled_strategies: List[str] = []

        logger.info(
            f"WalkForwardAnalyzer initialized: "
            f"IS={in_sample_days}d, OOS={out_of_sample_days}d, "
            f"window_type={window_type.value}, degradation_threshold={degradation_threshold_pct}%"
        )

    async def analyze(
        self,
        strategy_id: str,
        historical_data: Dict[datetime, Dict[str, Any]],
        optimize_fn: Callable,  # async fn(data) -> params
        backtest_fn: Callable,  # async fn(data, params) -> performance_score
    ) -> WalkForwardResult:
        """
        Perform walk-forward analysis on strategy.

        Args:
            strategy_id: Strategy identifier
            historical_data: Dict of {date: {price_data, ...}}
            optimize_fn: Async function to optimize parameters on in-sample data
            backtest_fn: Async function to evaluate on out-of-sample data

        Returns:
            WalkForwardResult with degradation analysis
        """
        logger.info(f"Starting walk-forward analysis for {strategy_id}")

        # Get sorted dates
        dates = sorted(historical_data.keys())

        if len(dates) < (self.in_sample_days + self.out_of_sample_days):
            logger.error(f"Insufficient data for walk-forward analysis")
            raise ValueError("Insufficient historical data")

        # Generate windows
        windows = await self._generate_windows(dates)

        if len(windows) < self.min_windows:
            logger.warning(
                f"Only {len(windows)} windows generated (min: {self.min_windows})"
            )

        # Analyze each window
        wf_windows = []
        for window in windows:
            wf_window = await self._analyze_window(
                strategy_id,
                window,
                historical_data,
                optimize_fn,
                backtest_fn,
            )
            wf_windows.append(wf_window)

        # Aggregate results
        result = await self._aggregate_results(strategy_id, wf_windows)

        # Store results
        if strategy_id not in self.results:
            self.results[strategy_id] = []
        self.results[strategy_id].append(result)

        # Check for degradation
        if result.degradation_detected:
            logger.warning(
                f"DEGRADATION DETECTED in {strategy_id}: "
                f"alpha_decay={result.average_alpha_decay_pct:.1f}%"
            )

            # Consider disabling strategy
            if result.average_alpha_decay_pct > self.degradation_threshold_pct:
                await self._disable_strategy(strategy_id, result)

        logger.info(
            f"Walk-forward analysis complete for {strategy_id}: "
            f"avg_IS={result.average_is_performance:.4f}, "
            f"avg_OOS={result.average_oos_performance:.4f}, "
            f"decay={result.average_alpha_decay_pct:.1f}%"
        )

        return result

    async def _generate_windows(
        self, dates: List[datetime]
    ) -> List[Tuple[int, int, int, int]]:
        """
        Generate window indices for walk-forward analysis.

        Returns:
            List of (train_start_idx, train_end_idx, test_start_idx, test_end_idx)
        """
        windows = []
        window_num = 0

        if self.window_type == WindowType.ROLLING:
            # Rolling window
            train_size = self.in_sample_days
            test_size = self.out_of_sample_days

            start_idx = 0
            while start_idx + train_size + test_size <= len(dates):
                train_start = start_idx
                train_end = start_idx + train_size
                test_start = train_end
                test_end = test_start + test_size

                windows.append((window_num, train_start, train_end, test_start, test_end))

                start_idx += self.step_days
                window_num += 1

        else:  # ANCHORED
            # Anchored window (training window grows)
            train_start = 0
            test_size = self.out_of_sample_days

            while train_start + self.in_sample_days + test_size <= len(dates):
                train_end = train_start + self.in_sample_days
                test_start = train_end
                test_end = test_start + test_size

                windows.append((window_num, train_start, train_end, test_start, test_end))

                train_start += self.step_days
                window_num += 1

        logger.debug(f"Generated {len(windows)} walk-forward windows")
        return windows

    async def _analyze_window(
        self,
        strategy_id: str,
        window: Tuple[int, int, int, int, int],
        historical_data: Dict[datetime, Any],
        optimize_fn: Callable,
        backtest_fn: Callable,
    ) -> WalkForwardWindow:
        """Analyze a single window"""
        window_num, train_start, train_end, test_start, test_end = window

        dates = sorted(historical_data.keys())
        train_dates = dates[train_start:train_end]
        test_dates = dates[test_start:test_end]

        train_data = {d: historical_data[d] for d in train_dates}
        test_data = {d: historical_data[d] for d in test_dates}

        try:
            # In-sample optimization
            start_date = train_dates[0] if train_dates else datetime.utcnow()
            end_date = train_dates[-1] if train_dates else datetime.utcnow()

            logger.debug(
                f"Window {window_num}: optimizing on {len(train_dates)} days "
                f"({start_date.date()}-{end_date.date()})"
            )

            params = await optimize_fn(train_data)
            is_performance = params.get("score", 0.0) if isinstance(params, dict) else 0.0

            # Out-of-sample validation
            test_start_date = test_dates[0] if test_dates else datetime.utcnow()
            test_end_date = test_dates[-1] if test_dates else datetime.utcnow()

            logger.debug(
                f"Window {window_num}: testing on {len(test_dates)} days "
                f"({test_start_date.date()}-{test_end_date.date()})"
            )

            oos_performance = await backtest_fn(test_data, params)

            # Calculate alpha decay
            if is_performance != 0:
                alpha_decay = ((is_performance - oos_performance) / is_performance) * 100
            else:
                alpha_decay = 0.0

            is_degraded = alpha_decay > self.degradation_threshold_pct

            return WalkForwardWindow(
                window_number=window_num,
                start_date=start_date,
                train_start=start_date,
                train_end=end_date,
                test_start=test_start_date,
                test_end=test_end_date,
                in_sample_performance=is_performance,
                out_of_sample_performance=oos_performance,
                alpha_decay_pct=alpha_decay,
                is_degraded=is_degraded,
            )

        except Exception as e:
            logger.error(f"Error analyzing window {window_num}: {e}")
            return WalkForwardWindow(
                window_number=window_num,
                start_date=dates[train_start] if train_start < len(dates) else datetime.utcnow(),
                train_start=dates[train_start] if train_start < len(dates) else datetime.utcnow(),
                train_end=dates[train_end - 1] if train_end <= len(dates) else datetime.utcnow(),
                test_start=dates[test_start] if test_start < len(dates) else datetime.utcnow(),
                test_end=dates[test_end - 1] if test_end <= len(dates) else datetime.utcnow(),
                is_degraded=True,
            )

    async def _aggregate_results(
        self, strategy_id: str, windows: List[WalkForwardWindow]
    ) -> WalkForwardResult:
        """Aggregate results across all windows"""
        if not windows:
            return WalkForwardResult(strategy_id=strategy_id)

        result = WalkForwardResult(
            strategy_id=strategy_id,
            total_windows=len(windows),
            windows=windows,
        )

        # Calculate averages
        is_scores = [w.in_sample_performance for w in windows]
        oos_scores = [w.out_of_sample_performance for w in windows]
        decay_scores = [w.alpha_decay_pct for w in windows]

        result.average_is_performance = sum(is_scores) / len(is_scores) if is_scores else 0.0
        result.average_oos_performance = sum(oos_scores) / len(oos_scores) if oos_scores else 0.0
        result.average_alpha_decay_pct = sum(decay_scores) / len(decay_scores) if decay_scores else 0.0

        # Find worst OOS window
        worst_window = min(windows, key=lambda w: w.out_of_sample_performance)
        result.worst_oos_window = worst_window

        # Check for degradation
        degraded_windows = [w for w in windows if w.is_degraded]
        result.degradation_detected = len(degraded_windows) > len(windows) * 0.3  # >30% degraded

        # Generate recommendation
        if result.average_alpha_decay_pct > self.degradation_threshold_pct:
            result.recommendation = "DISABLE - significant alpha decay"
        elif result.degradation_detected:
            result.recommendation = "MONITOR - performance degradation detected"
        elif result.average_oos_performance < result.average_is_performance * 0.5:
            result.recommendation = "REDUCE - poor out-of-sample performance"
        else:
            result.recommendation = "CONTINUE - acceptable walk-forward results"

        return result

    async def _disable_strategy(self, strategy_id: str, result: WalkForwardResult):
        """Disable strategy due to degradation"""
        if strategy_id not in self.disabled_strategies:
            self.disabled_strategies.append(strategy_id)

        logger.critical(
            f"Strategy {strategy_id} disabled: "
            f"alpha_decay={result.average_alpha_decay_pct:.1f}% "
            f"(threshold={self.degradation_threshold_pct}%)"
        )

    def get_analysis_report(self, strategy_id: str) -> Dict:
        """Generate walk-forward analysis report"""
        if strategy_id not in self.results:
            return {"error": f"No analysis for {strategy_id}"}

        results = self.results[strategy_id]
        latest = results[-1]

        return {
            "strategy_id": strategy_id,
            "timestamp": latest.timestamp.isoformat(),
            "total_windows": latest.total_windows,
            "performance": {
                "average_is_performance": latest.average_is_performance,
                "average_oos_performance": latest.average_oos_performance,
                "alpha_decay_pct": latest.average_alpha_decay_pct,
                "worst_oos_performance": (
                    latest.worst_oos_window.out_of_sample_performance
                    if latest.worst_oos_window else None
                ),
            },
            "degradation": {
                "detected": latest.degradation_detected,
                "threshold_pct": self.degradation_threshold_pct,
                "recommendation": latest.recommendation,
            },
            "windows": [
                {
                    "window_number": w.window_number,
                    "is_performance": w.in_sample_performance,
                    "oos_performance": w.out_of_sample_performance,
                    "alpha_decay_pct": w.alpha_decay_pct,
                    "is_degraded": w.is_degraded,
                    "train_period": f"{w.train_start.date()}-{w.train_end.date()}",
                    "test_period": f"{w.test_start.date()}-{w.test_end.date()}",
                }
                for w in latest.windows
            ],
        }

    def get_all_analysis_history(self) -> Dict[str, List[Dict]]:
        """Get analysis history for all strategies"""
        history = {}

        for strategy_id, results in self.results.items():
            history[strategy_id] = [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "total_windows": r.total_windows,
                    "average_is_performance": r.average_is_performance,
                    "average_oos_performance": r.average_oos_performance,
                    "alpha_decay_pct": r.average_alpha_decay_pct,
                    "degradation_detected": r.degradation_detected,
                    "recommendation": r.recommendation,
                }
                for r in results
            ]

        return history

    def is_strategy_disabled(self, strategy_id: str) -> bool:
        """Check if strategy is disabled"""
        return strategy_id in self.disabled_strategies

    def enable_strategy(self, strategy_id: str):
        """Re-enable strategy"""
        if strategy_id in self.disabled_strategies:
            self.disabled_strategies.remove(strategy_id)
            logger.info(f"Strategy {strategy_id} re-enabled")

    def get_disabled_strategies(self) -> List[str]:
        """Get list of disabled strategies"""
        return self.disabled_strategies.copy()
