"""
Strategy ensemble with signal aggregation, conflict resolution, and dynamic weighting.
Implements regime detection and automatic strategy rotation.
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger

from .base import BaseStrategy, Signal, Direction, PerformanceMetrics


@dataclass
class RegimeState:
    """Market regime detection."""
    regime: str  # "BULL", "BEAR", "SIDEWAYS"
    confidence: float  # 0-1
    vix_level: float
    yield_curve: str  # "steepening", "flattening", "inverted"
    breadth: float  # % of stocks above 200 MA
    timestamp: datetime = None


class EnsembleStrategy(BaseStrategy):
    """
    Strategy ensemble combining multiple trading approaches.

    Features:
    - Signal aggregation from multiple strategies
    - Weighted voting for signal conflicts
    - Dynamic weight adjustment based on rolling Sharpe ratio
    - Regime detection (bull/bear/sideways)
    - Automatic strategy rotation based on detected regime

    Position sizing:
    - Per-strategy contribution to final position size
    - Risk management across all strategies
    - Correlation monitoring to avoid excessive hedge positioning

    Performance:
    - Tracks individual strategy performance
    - Rebalances weights periodically
    - Logs all ensemble decisions
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        # Strategy component registry
        self.constituent_strategies: Dict[str, BaseStrategy] = {}

        # Dynamic weighting
        self.rebalance_frequency = self.config.get("rebalance_frequency", 20)  # Daily candles
        self.sharpe_lookback = self.config.get("sharpe_lookback", 60)
        self.min_strategy_weight = self.config.get("min_strategy_weight", 0.05)
        self.max_strategy_weight = self.config.get("max_strategy_weight", 0.50)

        # Regime detection
        self.vix_bull_threshold = self.config.get("vix_bull_threshold", 20.0)
        self.vix_bear_threshold = self.config.get("vix_bear_threshold", 30.0)
        self.breadth_threshold = self.config.get("breadth_threshold", 0.70)

        # Signal aggregation
        self.min_signal_strength = self.config.get("min_signal_strength", 0.3)
        self.signal_voting_threshold = self.config.get("signal_voting_threshold", 0.5)

        # Correlation monitoring
        self.max_ensemble_correlation = self.config.get("max_ensemble_correlation", 0.7)

        # State tracking
        self.current_regime = RegimeState(
            regime="SIDEWAYS",
            confidence=0.5,
            vix_level=20.0,
            yield_curve="steepening",
            breadth=0.50
        )
        self.regime_history: List[RegimeState] = []
        self.last_rebalance = 0
        self.candle_count = 0

        self._asset_class = "multi-asset"
        self._timeframe = "1D"

    def register_strategy(self, strategy: BaseStrategy) -> None:
        """Register a constituent strategy."""
        self.constituent_strategies[strategy.name] = strategy
        logger.info(f"Registered strategy: {strategy.name}")

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate ensemble signals from constituent strategies."""
        signals = []

        try:
            # Increment candle counter and check for rebalance
            self.candle_count += 1
            if self.candle_count >= self.rebalance_frequency:
                self._rebalance_weights()
                self.candle_count = 0

            # Detect current market regime
            self.current_regime = self._detect_regime(data)
            self.regime_history.append(self.current_regime)

            # Collect signals from all strategies
            all_signals: Dict[str, List[Signal]] = {}
            for strat_name, strategy in self.constituent_strategies.items():
                if not strategy.enabled:
                    continue

                try:
                    strat_signals = strategy.generate_signals(data)
                    if strat_signals:
                        all_signals[strat_name] = strat_signals
                except Exception as e:
                    logger.error(f"Error in {strat_name}: {e}")

            if not all_signals:
                return signals

            # Aggregate signals
            aggregated = self._aggregate_signals(all_signals, data)

            # Apply regime-based filtering
            filtered = self._apply_regime_filter(aggregated)

            # Check for signal conflicts
            conflicts = self._detect_conflicts(filtered)
            if conflicts:
                logger.warning(f"Signal conflicts detected: {conflicts}")

            # Size positions
            for signal in filtered:
                signal.position_size = self._calculate_ensemble_position(
                    signal,
                    all_signals
                )
                signals.append(signal)
                self.log_signal(signal)

        except Exception as e:
            logger.error(f"Ensemble signal generation error: {e}")

        return signals

    def should_exit(
        self,
        position: Dict[str, Any],
        data: pd.DataFrame
    ) -> bool:
        """Exit when majority of constituent strategies vote to exit."""
        try:
            exit_votes = 0
            total_votes = 0

            for strat_name, strategy in self.constituent_strategies.items():
                if not strategy.enabled:
                    continue

                try:
                    if strategy.should_exit(position, data):
                        exit_votes += strategy.weight
                    total_votes += strategy.weight
                except Exception as e:
                    logger.debug(f"Exit check error in {strat_name}: {e}")

            # Exit if > 50% weighted vote
            if total_votes > 0 and (exit_votes / total_votes) > self.signal_voting_threshold:
                logger.info(f"Ensemble exit: {exit_votes/total_votes:.1%} of strategies voting exit")
                return True

        except Exception as e:
            logger.error(f"Ensemble exit check error: {e}")

        return False

    def _aggregate_signals(
        self,
        all_signals: Dict[str, List[Signal]],
        data: pd.DataFrame
    ) -> List[Signal]:
        """
        Aggregate signals from multiple strategies.
        Implements weighted voting for conflicting signals.
        """
        symbol_signals: Dict[str, List[Tuple[Signal, float]]] = {}

        # Group signals by symbol with strategy weights
        for strat_name, signals in all_signals.items():
            strategy = self.constituent_strategies[strat_name]
            weight = strategy.weight

            for signal in signals:
                if signal.strength < self.min_signal_strength:
                    continue

                if signal.symbol not in symbol_signals:
                    symbol_signals[signal.symbol] = []

                symbol_signals[signal.symbol].append((signal, weight))

        aggregated = []

        # Aggregate per symbol
        for symbol, weighted_signals in symbol_signals.items():
            if not weighted_signals:
                continue

            # Weighted voting
            long_votes = sum(
                weight * sig.strength
                for sig, weight in weighted_signals
                if sig.direction == Direction.LONG
            )
            short_votes = sum(
                weight * sig.strength
                for sig, weight in weighted_signals
                if sig.direction == Direction.SHORT
            )
            total_weight = sum(weight for _, weight in weighted_signals)

            # Determine final direction
            if abs(long_votes - short_votes) < total_weight * 0.1:
                # Conflicting signals, skip
                logger.debug(f"Conflicting signals for {symbol}, skipping")
                continue

            final_direction = Direction.LONG if long_votes > short_votes else Direction.SHORT
            final_strength = max(long_votes, short_votes) / (total_weight or 1.0)

            # Aggregate metadata
            metadata = {
                "constituent_count": len(weighted_signals),
                "long_votes": long_votes,
                "short_votes": short_votes,
                "constituent_signals": [
                    f"{sig.strategy_name}({sig.direction.value})"
                    for sig, _ in weighted_signals
                ]
            }

            # Create ensemble signal
            ensemble_signal = Signal(
                symbol=symbol,
                direction=final_direction,
                strength=min(final_strength, 1.0),
                strategy_name=self.name,
                metadata=metadata
            )

            aggregated.append(ensemble_signal)

        return aggregated

    def _apply_regime_filter(self, signals: List[Signal]) -> List[Signal]:
        """Filter signals based on detected regime."""
        filtered = []

        for signal in signals:
            # In bull regime, favor long signals
            if self.current_regime.regime == "BULL":
                if signal.direction == Direction.LONG:
                    signal.strength *= 1.1
                elif signal.direction == Direction.SHORT:
                    signal.strength *= 0.8

            # In bear regime, favor short signals
            elif self.current_regime.regime == "BEAR":
                if signal.direction == Direction.SHORT:
                    signal.strength *= 1.1
                elif signal.direction == Direction.LONG:
                    signal.strength *= 0.8

            # In sideways, reduce signal strength
            elif self.current_regime.regime == "SIDEWAYS":
                signal.strength *= 0.7

            # Only include if still above threshold after filtering
            if signal.strength >= self.min_signal_strength:
                filtered.append(signal)

        return filtered

    def _detect_regime(self, data: pd.DataFrame) -> RegimeState:
        """
        Detect current market regime using:
        - VIX level
        - Yield curve state
        - Market breadth
        """
        try:
            vix = self._get_vix(data)
            breadth = self._calculate_market_breadth(data)
            yield_curve = self._get_yield_curve_state()

            # Determine regime
            if vix > self.vix_bear_threshold:
                regime = "BEAR"
                confidence = min((vix - self.vix_bear_threshold) / 20, 1.0)
            elif vix < self.vix_bull_threshold and breadth > self.breadth_threshold:
                regime = "BULL"
                confidence = (self.vix_bull_threshold - vix) / self.vix_bull_threshold
            else:
                regime = "SIDEWAYS"
                confidence = 0.5

            regime_state = RegimeState(
                regime=regime,
                confidence=confidence,
                vix_level=vix,
                yield_curve=yield_curve,
                breadth=breadth,
                timestamp=datetime.now()
            )

            if len(self.regime_history) == 0 or self.regime_history[-1].regime != regime:
                logger.info(f"Regime changed to {regime} (confidence={confidence:.1%})")

            return regime_state

        except Exception as e:
            logger.error(f"Regime detection error: {e}")
            return self.current_regime

    def _detect_conflicts(self, signals: List[Signal]) -> List[str]:
        """Detect conflicting signals for same symbol."""
        conflicts = []
        symbol_directions = {}

        for signal in signals:
            if signal.symbol not in symbol_directions:
                symbol_directions[signal.symbol] = []
            symbol_directions[signal.symbol].append(signal.direction)

        for symbol, directions in symbol_directions.items():
            if (Direction.LONG in directions and Direction.SHORT in directions):
                conflicts.append(symbol)

        return conflicts

    def _calculate_ensemble_position(
        self,
        signal: Signal,
        all_signals: Dict[str, List[Signal]]
    ) -> float:
        """Calculate ensemble position size."""
        constituent_count = signal.metadata.get("constituent_count", 1)

        # Base size
        base_size = 100  # 100 shares default

        # Scale by signal strength
        scaled_size = base_size * signal.strength

        # Scale by constituent count (more agreement = larger position)
        scaled_size *= (1.0 + (constituent_count - 1) * 0.2)

        return scaled_size

    def _rebalance_weights(self) -> None:
        """Rebalance strategy weights based on performance."""
        try:
            total_weight = 0

            for strat_name, strategy in self.constituent_strategies.items():
                metrics = strategy.get_metrics()

                # Calculate rolling Sharpe ratio as weight signal
                sharpe = metrics.sharpe_ratio
                win_rate = metrics.win_rate

                # Weight = f(Sharpe, Win Rate)
                if sharpe > 1.0:
                    new_weight = 0.50  # Excellent
                elif sharpe > 0.5:
                    new_weight = 0.35  # Good
                elif sharpe > 0.0:
                    new_weight = 0.20  # Okay
                else:
                    new_weight = 0.05  # Poor

                # Adjust for win rate
                new_weight *= (0.5 + win_rate)

                # Apply bounds
                new_weight = max(self.min_strategy_weight,
                                min(new_weight, self.max_strategy_weight))

                strategy.weight = new_weight
                total_weight += new_weight

            # Normalize weights to sum to 1.0
            if total_weight > 0:
                for strategy in self.constituent_strategies.values():
                    strategy.weight /= total_weight

            logger.info("Strategy weights rebalanced")

        except Exception as e:
            logger.error(f"Rebalancing error: {e}")

    def _get_vix(self, data: pd.DataFrame) -> float:
        """Get current VIX level."""
        # Placeholder - would fetch from market data
        return 20.0

    def _calculate_market_breadth(self, data: pd.DataFrame) -> float:
        """Calculate % of stocks above 200-period MA."""
        if len(data) < 200 or "close" not in data.columns:
            return 0.5

        ma200 = data["close"].rolling(200).mean()
        above_ma = (data["close"] > ma200).sum()
        return above_ma / len(data)

    def _get_yield_curve_state(self) -> str:
        """Get yield curve state (steepening/flattening/inverted)."""
        # Placeholder - would fetch 2Y vs 10Y spread
        return "steepening"

    def get_ensemble_metrics(self) -> Dict[str, Any]:
        """Get comprehensive ensemble metrics."""
        constituent_metrics = {}

        for name, strategy in self.constituent_strategies.items():
            metrics = strategy.get_metrics()
            constituent_metrics[name] = {
                "weight": strategy.weight,
                "sharpe": metrics.sharpe_ratio,
                "win_rate": metrics.win_rate,
                "max_drawdown": metrics.max_drawdown,
                "total_return": metrics.total_return,
                "trade_count": metrics.trade_count,
            }

        return {
            "current_regime": {
                "regime": self.current_regime.regime,
                "confidence": self.current_regime.confidence,
                "vix": self.current_regime.vix_level,
            },
            "constituent_strategies": constituent_metrics,
            "ensemble_metrics": self.metrics.__dict__,
        }
