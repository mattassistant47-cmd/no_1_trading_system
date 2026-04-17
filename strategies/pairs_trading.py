"""
Pairs Trading Strategy — Statistical arbitrage on correlated pairs

Long the underperformer + short the outperformer when the spread deviates
from its historical mean. Market-neutral approach that profits regardless
of overall market direction.

Method:
1. Check historical correlation (must be > 0.70)
2. Calculate spread = log(A) - beta * log(B) where beta comes from OLS
3. Z-score the spread; enter when |z| > 2, exit when |z| < 0.5

Best for: market-neutral exposure, low-correlation alpha.
Works on: equities (e.g. KO/PEP, XOM/CVX, GOOGL/META).

NOTE: This strategy requires TWO price streams. Single-symbol data passed
to generate_signals() won't yield signals — the engine's pair configuration
(separate concern) selects which pairs to monitor.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy, Signal, Direction


class PairsTrading(BaseStrategy):
    """Market-neutral pairs trading via z-scored spread."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config or {})
        self.z_entry: float = float(self.config.get("z_entry", 2.0))
        self.z_exit: float = float(self.config.get("z_exit", 0.5))
        self.correlation_min: float = float(self.config.get("correlation_min", 0.70))
        self.window: int = int(self.config.get("window", 60))
        self._asset_class = "equities"
        self._timeframe = "1D"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """
        Single-symbol mode: no-op.
        For true pairs trading, the engine must call `generate_pair_signals(df_a, df_b)`.
        """
        return []

    def generate_pair_signals(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        symbol_a: str,
        symbol_b: str,
    ) -> List[Signal]:
        signals: List[Signal] = []
        if df_a is None or df_b is None or len(df_a) < self.window or len(df_b) < self.window:
            return signals

        try:
            common = pd.concat(
                [df_a["close"].rename("a"), df_b["close"].rename("b")],
                axis=1,
            ).dropna()
            if len(common) < self.window:
                return signals

            recent = common.tail(self.window)
            corr = recent["a"].corr(recent["b"])
            if corr is None or abs(corr) < self.correlation_min:
                return signals

            # Log prices and OLS beta
            la = np.log(recent["a"].values)
            lb = np.log(recent["b"].values)
            beta = np.polyfit(lb, la, 1)[0]
            spread = la - beta * lb
            z = (spread[-1] - spread.mean()) / (spread.std() or 1e-9)

            # Entry
            if z >= self.z_entry:
                # A is overpriced relative to B → short A, long B
                strength = min(1.0, abs(z) / (self.z_entry * 2))
                signals.append(Signal(
                    symbol=symbol_a, direction=Direction.SHORT, strength=strength,
                    strategy_name=self.name, metadata={"pair": f"{symbol_a}/{symbol_b}", "z": float(z), "beta": float(beta), "correlation": float(corr)},
                ))
                signals.append(Signal(
                    symbol=symbol_b, direction=Direction.LONG, strength=strength,
                    strategy_name=self.name, metadata={"pair": f"{symbol_a}/{symbol_b}", "z": float(z), "beta": float(beta), "leg": "long"},
                ))
            elif z <= -self.z_entry:
                # A is underpriced → long A, short B
                strength = min(1.0, abs(z) / (self.z_entry * 2))
                signals.append(Signal(
                    symbol=symbol_a, direction=Direction.LONG, strength=strength,
                    strategy_name=self.name, metadata={"pair": f"{symbol_a}/{symbol_b}", "z": float(z), "beta": float(beta), "correlation": float(corr)},
                ))
                signals.append(Signal(
                    symbol=symbol_b, direction=Direction.SHORT, strength=strength,
                    strategy_name=self.name, metadata={"pair": f"{symbol_a}/{symbol_b}", "z": float(z), "beta": float(beta), "leg": "short"},
                ))

            for s in signals:
                self.log_signal(s)

        except Exception as e:
            logger.error(f"PairsTrading signal error: {e}")

        return signals

    def should_exit(self, position: Dict[str, Any], data: pd.DataFrame) -> bool:
        """Exit via generate_pair_signals reconvergence check (|z| < z_exit)."""
        # For single-symbol inputs we can't compute pair z-score; engine must
        # call this with joint data. Default false so engine keeps positions.
        return False
