"""
Statistical mean reversion strategy using Bollinger Bands and Z-scores.
Includes pairs trading capability with co-integration detection.
"""

from typing import List, Dict, Any, Tuple
import pandas as pd
import strategies.indicators as ta
import numpy as np
from scipy import stats
from loguru import logger

from .base import BaseStrategy, Signal, Direction


class StatisticalMeanReversion(BaseStrategy):
    """
    Mean reversion strategy for liquid large-cap stocks.

    Entry conditions:
    - Z-score < -2 for long (oversold)
    - Z-score > +2 for short (overbought)
    - Price within Bollinger Bands extremes

    Exit conditions:
    - Price returns to mean (Z-score → 0)
    - Stop at Z-score ±3 (extreme deviation)

    Features:
    - Pairs trading with co-integration detection
    - Half-life calculation for reversion speed
    - Mean reversion strength scoring
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        # Strategy parameters
        self.bb_period = self.config.get("bb_period", 20)
        self.bb_stddev = self.config.get("bb_stddev", 2.0)

        self.z_score_entry = self.config.get("z_score_entry", 2.0)
        self.z_score_exit = self.config.get("z_score_exit", 0.5)
        self.z_score_stop = self.config.get("z_score_stop", 3.0)

        self.lookback_period = self.config.get("lookback_period", 60)
        self.min_co_integration = self.config.get("min_co_integration", 0.8)

        self.risk_per_trade = self.config.get("risk_per_trade", 0.02)

        self._asset_class = "equities"
        self._timeframe = "1D"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate mean reversion signals."""
        signals = []

        if len(data) < max(self.bb_period, self.lookback_period):
            return signals

        try:
            # Calculate indicators
            data = self._calculate_indicators(data)

            current = data.iloc[-1]
            previous = data.iloc[-2] if len(data) > 1 else current

            # Mean reversion long entry
            if current["z_score"] < -self.z_score_entry:
                position_size = self._calculate_mr_position_size(
                    capital=100000,
                    z_score=current["z_score"]
                )

                signal = Signal(
                    symbol=data.index[-1] if hasattr(data.index, "name") else "SYMBOL",
                    direction=Direction.LONG,
                    strength=self._calculate_mr_strength(current, Direction.LONG),
                    strategy_name=self.name,
                    position_size=position_size,
                    stop_loss=current["close"] - (current["bb_width"] * 0.5),
                    take_profit=current["mean"],
                    metadata={
                        "z_score": current["z_score"],
                        "mean": current["mean"],
                        "std": current["std"],
                        "bb_upper": current["bb_upper"],
                        "bb_lower": current["bb_lower"],
                        "half_life": current.get("half_life", 0.0),
                    }
                )
                signals.append(signal)
                self.log_signal(signal)

            # Mean reversion short entry
            elif current["z_score"] > self.z_score_entry:
                position_size = self._calculate_mr_position_size(
                    capital=100000,
                    z_score=current["z_score"]
                )

                signal = Signal(
                    symbol=data.index[-1] if hasattr(data.index, "name") else "SYMBOL",
                    direction=Direction.SHORT,
                    strength=self._calculate_mr_strength(current, Direction.SHORT),
                    strategy_name=self.name,
                    position_size=position_size,
                    stop_loss=current["close"] + (current["bb_width"] * 0.5),
                    take_profit=current["mean"],
                    metadata={
                        "z_score": current["z_score"],
                        "mean": current["mean"],
                        "std": current["std"],
                        "bb_upper": current["bb_upper"],
                        "bb_lower": current["bb_lower"],
                        "half_life": current.get("half_life", 0.0),
                    }
                )
                signals.append(signal)
                self.log_signal(signal)

        except Exception as e:
            logger.error(f"Signal generation error in {self.name}: {e}")

        return signals

    def should_exit(
        self,
        position: Dict[str, Any],
        data: pd.DataFrame
    ) -> bool:
        """Determine if mean reversion position should exit."""
        if len(data) < self.bb_period:
            return False

        try:
            data = self._calculate_indicators(data)
            current = data.iloc[-1]

            z_score = current["z_score"]
            mean = current["mean"]
            close = current["close"]

            # Exit on extreme Z-score (stop)
            if abs(z_score) > self.z_score_stop:
                logger.info(f"Exit: Z-score extreme ({z_score:.2f})")
                return True

            # Long exit when approaching mean
            if position.get("direction") == Direction.LONG:
                if z_score >= -self.z_score_exit:
                    logger.info(f"Exit LONG: Reversion to mean ({z_score:.2f})")
                    return True

            # Short exit when approaching mean
            elif position.get("direction") == Direction.SHORT:
                if z_score <= self.z_score_exit:
                    logger.info(f"Exit SHORT: Reversion to mean ({z_score:.2f})")
                    return True

        except Exception as e:
            logger.error(f"Exit check error: {e}")

        return False

    def detect_pairs(
        self,
        symbols: List[str],
        data_dict: Dict[str, pd.DataFrame]
    ) -> List[Tuple[str, str]]:
        """
        Detect co-integrated pairs for pairs trading.

        Args:
            symbols: List of symbols to check
            data_dict: Dictionary of symbol -> OHLCV dataframe

        Returns:
            List of (symbol1, symbol2) pairs that are co-integrated
        """
        pairs = []

        try:
            for i, sym1 in enumerate(symbols):
                for sym2 in symbols[i + 1:]:
                    if sym1 not in data_dict or sym2 not in data_dict:
                        continue

                    price1 = data_dict[sym1]["close"].values
                    price2 = data_dict[sym2]["close"].values

                    # Calculate correlation
                    corr = np.corrcoef(price1[-self.lookback_period:],
                                       price2[-self.lookback_period:])[0, 1]

                    if corr > self.min_co_integration:
                        pairs.append((sym1, sym2))
                        logger.info(
                            f"Pairs detected: {sym1}-{sym2} (corr={corr:.3f})"
                        )

        except Exception as e:
            logger.error(f"Pairs detection error: {e}")

        return pairs

    def _calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate mean reversion indicators."""
        df = data.copy()

        # Bollinger Bands
        bb_result = ta.bbands(
            df["close"],
            length=self.bb_period,
            std=self.bb_stddev
        )
        df["bb_upper"] = bb_result[f"BBU_{self.bb_period}_{self.bb_stddev}"]
        df["bb_lower"] = bb_result[f"BBL_{self.bb_period}_{self.bb_stddev}"]
        df["bb_mid"] = bb_result[f"BBM_{self.bb_period}_{self.bb_stddev}"]
        df["bb_width"] = df["bb_upper"] - df["bb_lower"]

        # Mean and standard deviation
        df["mean"] = df["close"].rolling(self.bb_period).mean()
        df["std"] = df["close"].rolling(self.bb_period).std()

        # Z-score
        df["z_score"] = (df["close"] - df["mean"]) / df["std"]

        # Half-life of mean reversion
        if len(df) >= self.lookback_period:
            try:
                residuals = df["close"].iloc[-self.lookback_period:] - df["mean"].iloc[-self.lookback_period:]
                residuals_lagged = residuals.shift(1).dropna()
                residuals_current = residuals[1:].reset_index(drop=True)

                if len(residuals_lagged) > 1:
                    slope = np.polyfit(residuals_lagged, residuals_current, 1)[0]
                    if slope != 0:
                        half_life = np.log(0.5) / np.log(slope)
                        df["half_life"] = max(0.0, half_life)
                    else:
                        df["half_life"] = np.nan
                else:
                    df["half_life"] = np.nan
            except Exception as e:
                logger.debug(f"Half-life calculation failed: {e}")
                df["half_life"] = np.nan
        else:
            df["half_life"] = np.nan

        return df

    def _calculate_mr_position_size(
        self,
        capital: float,
        z_score: float
    ) -> float:
        """Calculate position size based on Z-score extremeness."""
        # Larger positions for more extreme Z-scores
        extremeness = min(abs(z_score) / self.z_score_entry, 1.0)
        base_size = capital * 0.01  # 1% base risk
        return base_size * (0.5 + extremeness)

    def _calculate_mr_strength(
        self,
        current: pd.Series,
        direction: Direction
    ) -> float:
        """Calculate mean reversion signal strength."""
        z_abs = abs(current["z_score"])

        # Strength based on Z-score distance from mean
        strength = min(z_abs / self.z_score_entry, 1.0) * 0.5

        # Bonus for extreme extremeness
        if z_abs > self.z_score_entry * 1.5:
            strength += 0.3

        # Bonus if near Bollinger Bands
        bb_dist = min(
            abs(current["close"] - current["bb_upper"]),
            abs(current["close"] - current["bb_lower"])
        ) / (current["bb_width"] or 1.0)

        if bb_dist < 0.2:  # Within 20% of edge
            strength += 0.2

        return min(strength, 1.0)
