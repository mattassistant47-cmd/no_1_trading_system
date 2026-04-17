"""
Trend Following Strategy — Long-horizon SMA crossover

Classic trend-following system (Turtle-style) that holds positions through
multi-week trends. Different from short-term Momentum — this targets the
50/200 SMA "Golden Cross" / "Death Cross" pattern for position trading.

Entry LONG: fast_sma crosses above slow_sma (Golden Cross)
Entry SHORT: fast_sma crosses below slow_sma (Death Cross)
Exit: opposite crossover, or 10% trailing stop

Best for: sustained bull/bear trends, low-frequency trading.
Works on: equities, crypto (on larger timeframes).
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy, Signal, Direction
import strategies.indicators as ta


class TrendFollowing(BaseStrategy):
    """Long-term trend following via SMA crossover."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config or {})
        self.fast: int = int(self.config.get("fast_sma", 50))
        self.slow: int = int(self.config.get("slow_sma", 200))
        self.trail_pct: float = float(self.config.get("trail_pct", 0.10))
        self._asset_class = self.config.get("asset_class", "equities")
        self._timeframe = "1D"

    def _sma(self, series: pd.Series, length: int) -> pd.Series:
        return series.rolling(length).mean()

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        signals: List[Signal] = []
        if data is None or len(data) < self.slow + 2:
            return signals

        try:
            df = data.copy()
            df["fast"] = self._sma(df["close"], self.fast)
            df["slow"] = self._sma(df["close"], self.slow)

            cur = df.iloc[-1]
            prev = df.iloc[-2]

            if pd.isna(cur["fast"]) or pd.isna(cur["slow"]) or pd.isna(prev["fast"]) or pd.isna(prev["slow"]):
                return signals

            close = float(cur["close"])
            symbol = str(data.index[-1]) if hasattr(data.index, "name") and data.index.name else "SYMBOL"

            # Golden cross
            if prev["fast"] <= prev["slow"] and cur["fast"] > cur["slow"]:
                stop = close * (1 - self.trail_pct)
                sig = Signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=0.70,
                    strategy_name=self.name,
                    stop_loss=stop,
                    metadata={"type": "golden_cross", "fast": float(cur["fast"]), "slow": float(cur["slow"])},
                )
                signals.append(sig)
                self.log_signal(sig)

            # Death cross
            elif prev["fast"] >= prev["slow"] and cur["fast"] < cur["slow"]:
                stop = close * (1 + self.trail_pct)
                sig = Signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=0.70,
                    strategy_name=self.name,
                    stop_loss=stop,
                    metadata={"type": "death_cross", "fast": float(cur["fast"]), "slow": float(cur["slow"])},
                )
                signals.append(sig)
                self.log_signal(sig)

        except Exception as e:
            logger.error(f"TrendFollowing signal error: {e}")

        return signals

    def should_exit(self, position: Dict[str, Any], data: pd.DataFrame) -> bool:
        if data is None or len(data) < self.slow + 1:
            return False
        try:
            df = data.copy()
            df["fast"] = self._sma(df["close"], self.fast)
            df["slow"] = self._sma(df["close"], self.slow)
            cur = df.iloc[-1]
            direction = position.get("direction")
            if direction == Direction.LONG and cur["fast"] < cur["slow"]:
                return True
            if direction == Direction.SHORT and cur["fast"] > cur["slow"]:
                return True
            # Trailing stop
            close = float(cur["close"])
            stop = position.get("stop_loss", 0)
            if direction == Direction.LONG and close <= stop:
                return True
            if direction == Direction.SHORT and close >= stop:
                return True
        except Exception as e:
            logger.debug(f"TrendFollowing exit check error: {e}")
        return False
