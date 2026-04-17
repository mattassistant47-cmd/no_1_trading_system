"""
Volatility Regime Strategy — VIX-based position sizing / exposure

Not a signal-generator in the traditional sense. Instead, this is a
regime detector that OTHER strategies should consult to scale up/down:

- VIX < 15   → low-vol regime → scale up trending strategies
- 15 ≤ VIX ≤ 25 → normal regime → standard sizing
- VIX > 25   → high-vol regime → scale down, prefer mean reversion

Emits meta-signals via metadata so the engine can adjust allocation.

Best for: portfolio-level risk regime awareness.
Works on: indirectly on all asset classes.

NOTE: Requires VIX data stream. If VIX data unavailable, falls back to
realized vol from SPY (standard deviation of returns over N days).
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy, Signal, Direction


class VolatilityRegime(BaseStrategy):
    """Detects volatility regime and emits advisory meta-signals."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config or {})
        self.vix_low: float = float(self.config.get("vix_low", 15.0))
        self.vix_high: float = float(self.config.get("vix_high", 25.0))
        self.vol_window: int = int(self.config.get("vol_window", 20))
        self._asset_class = "meta"
        self._timeframe = "1D"
        self._last_regime: Optional[str] = None

    def _realized_vol(self, close: pd.Series) -> float:
        """Annualized realized vol as VIX proxy when VIX feed unavailable."""
        if len(close) < self.vol_window + 1:
            return 0.0
        returns = np.log(close / close.shift(1)).dropna().tail(self.vol_window)
        if len(returns) < 2:
            return 0.0
        # Annualized percentage vol
        return float(returns.std() * np.sqrt(252) * 100)

    def classify_regime(self, vol: float) -> str:
        if vol <= 0:
            return "unknown"
        if vol < self.vix_low:
            return "low"
        if vol > self.vix_high:
            return "high"
        return "normal"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Emit meta-signals describing current volatility regime.

        The engine can subscribe to these (direction=NEUTRAL) and adjust
        sizing on trending/mean-reverting strategies accordingly.
        """
        signals: List[Signal] = []
        if data is None or len(data) < self.vol_window + 1:
            return signals

        try:
            # Prefer explicit VIX column if present
            if "vix" in data.columns:
                vol = float(data["vix"].iloc[-1])
            else:
                vol = self._realized_vol(data["close"])

            regime = self.classify_regime(vol)
            if regime == "unknown":
                return signals

            # Only emit on regime change to avoid noise
            if regime == self._last_regime:
                return signals
            self._last_regime = regime

            symbol = str(data.index[-1]) if hasattr(data.index, "name") and data.index.name else "REGIME"
            sig = Signal(
                symbol=symbol,
                direction=Direction.NEUTRAL,
                strength=min(1.0, vol / 40.0),
                strategy_name=self.name,
                metadata={
                    "type": "regime_change",
                    "regime": regime,
                    "volatility": vol,
                    "advice": {
                        "low": "scale_up_trend",
                        "normal": "standard_sizing",
                        "high": "scale_down_prefer_mean_reversion",
                    }.get(regime, "standard_sizing"),
                },
            )
            signals.append(sig)
            self.log_signal(sig)
            logger.info(f"Volatility regime changed to {regime} (vol={vol:.2f})")

        except Exception as e:
            logger.error(f"VolatilityRegime signal error: {e}")

        return signals

    def should_exit(self, position: Dict[str, Any], data: pd.DataFrame) -> bool:
        return False  # meta-strategy, doesn't hold positions
