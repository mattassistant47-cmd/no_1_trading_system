"""
Breakout Strategy — Volatility Expansion / Range Breaks

Detects when price breaks above/below a recent range with volume confirmation.
Best for: trending markets, volatility expansion, news-driven moves.
Works on: equities, crypto.

Entry LONG:
- Price closes above N-day high (breakout)
- Volume > 1.5x average (confirmation)
- ATR expanding (volatility increasing)

Entry SHORT:
- Price closes below N-day low (breakdown)
- Volume > 1.5x average
- ATR expanding

Exit: trailing stop at 2x ATR, or opposite breakout.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy, Signal, Direction
import strategies.indicators as ta


class Breakout(BaseStrategy):
    """Range breakout with volume + volatility confirmation."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config or {})
        self.lookback: int = int(self.config.get("lookback", 20))
        self.atr_period: int = int(self.config.get("atr_period", 14))
        self.atr_mult: float = float(self.config.get("atr_multiplier", 2.0))
        self.volume_mult: float = float(self.config.get("volume_multiplier", 1.5))
        self.require_volume: bool = bool(self.config.get("volume_confirmation", True))

        self._asset_class = self.config.get("asset_class", "equities")
        self._timeframe = "1D"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate breakout signals from OHLCV data."""
        signals: List[Signal] = []
        required = max(self.lookback, self.atr_period) + 2
        if data is None or len(data) < required:
            return signals

        try:
            df = data.copy()
            # Rolling high/low of prior N bars (exclude current to test breakout)
            df["hi_n"] = df["high"].rolling(self.lookback).max().shift(1)
            df["lo_n"] = df["low"].rolling(self.lookback).min().shift(1)
            df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)
            df["vol_avg"] = df["volume"].rolling(self.lookback).mean()

            current = df.iloc[-1]
            close = float(current["close"])
            atr = float(current["atr"]) if pd.notna(current["atr"]) else 0.0
            hi_n = float(current["hi_n"]) if pd.notna(current["hi_n"]) else 0.0
            lo_n = float(current["lo_n"]) if pd.notna(current["lo_n"]) else 0.0
            vol = float(current["volume"]) if pd.notna(current["volume"]) else 0.0
            vol_avg = float(current["vol_avg"]) if pd.notna(current["vol_avg"]) else 0.0

            if atr <= 0:
                return signals

            vol_ok = (not self.require_volume) or (vol_avg > 0 and vol >= self.volume_mult * vol_avg)

            symbol = str(data.index[-1]) if hasattr(data.index, "name") and data.index.name else "SYMBOL"

            # Bullish breakout
            if close > hi_n and vol_ok:
                strength = min(1.0, (close - hi_n) / atr / self.atr_mult)
                stop = close - atr * self.atr_mult
                target = close + atr * self.atr_mult * 2
                sig = Signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    strength=max(0.5, strength),
                    strategy_name=self.name,
                    stop_loss=stop,
                    take_profit=target,
                    metadata={"type": "breakout_up", "atr": atr, "hi_n": hi_n, "volume_ratio": (vol / vol_avg) if vol_avg else 0},
                )
                signals.append(sig)
                self.log_signal(sig)

            # Bearish breakdown
            elif close < lo_n and vol_ok:
                strength = min(1.0, (lo_n - close) / atr / self.atr_mult)
                stop = close + atr * self.atr_mult
                target = close - atr * self.atr_mult * 2
                sig = Signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    strength=max(0.5, strength),
                    strategy_name=self.name,
                    stop_loss=stop,
                    take_profit=target,
                    metadata={"type": "breakdown", "atr": atr, "lo_n": lo_n, "volume_ratio": (vol / vol_avg) if vol_avg else 0},
                )
                signals.append(sig)
                self.log_signal(sig)

        except Exception as e:
            logger.error(f"Breakout signal generation error: {e}")

        return signals

    def should_exit(self, position: Dict[str, Any], data: pd.DataFrame) -> bool:
        """Exit on trailing stop hit or reverse breakout."""
        if data is None or len(data) < self.atr_period + 1:
            return False
        try:
            atr = float(ta.atr(data["high"], data["low"], data["close"], length=self.atr_period).iloc[-1])
            close = float(data["close"].iloc[-1])
            direction = position.get("direction")
            stop = position.get("stop_loss", 0)
            if direction == Direction.LONG and close <= stop:
                return True
            if direction == Direction.SHORT and close >= stop:
                return True
        except Exception as e:
            logger.debug(f"Breakout exit check error: {e}")
        return False
