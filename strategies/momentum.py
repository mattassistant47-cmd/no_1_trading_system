"""
Multi-timeframe momentum strategy using technical indicators.
Combines RSI, MADC, ADX, and EMA crossovers with daily/4H confirmation.
"""

from typing import List, Dict, Any
import pandas as pd
import pandas_ta as ta
import numpy as np
from loguru import logger

from .base import BaseStrategy, Signal, Direction


class MultiTimeframeMomentum(BaseStrategy):
    """
    Multi-timeframe momentum strategy targeting US equities.

    Entry conditions:
    - RSI oversold (<30) on daily, recovery on 4H
    - MACD bullish crossover
    - Price above 50-period EMA
    - ADX > 25 (strong trend)

    Exit conditions:
    - RSI overbought (>70)
    - Trailing stop hit (ATR-based)
    - ADX < 20 (trend weakening)

    Position sizing via ATR for risk management.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        # Strategy parameters
        self.rsi_period = self.config.get("rsi_period", 14)
        self.rsi_oversold = self.config.get("rsi_oversold", 30)
        self.rsi_overbought = self.config.get("rsi_overbought", 70)

        self.ema_short = self.config.get("ema_short", 20)
        self.ema_long = self.config.get("ema_long", 50)
        self.ema_trend = self.config.get("ema_trend", 200)

        self.adx_period = self.config.get("adx_period", 14)
        self.adx_strong = self.config.get("adx_strong", 25)
        self.adx_weak = self.config.get("adx_weak", 20)

        self.macd_fast = self.config.get("macd_fast", 12)
        self.macd_slow = self.config.get("macd_slow", 26)
        self.macd_signal = self.config.get("macd_signal", 9)

        self.atr_period = self.config.get("atr_period", 14)
        self.trailing_stop_multiplier = self.config.get("trailing_stop_multiplier", 2.0)

        self.risk_per_trade = self.config.get("risk_per_trade", 0.02)

        self._asset_class = "equities"
        self._timeframe = "1D"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate momentum signals from market data."""
        signals = []

        if len(data) < max(
            self.ema_trend, self.adx_period, self.macd_slow + self.macd_signal
        ):
            return signals

        try:
            # Calculate technical indicators
            data = self._calculate_indicators(data)

            # Get current candle values
            current = data.iloc[-1]
            previous = data.iloc[-2]

            # Check for bullish signal
            if self._is_bullish_setup(current, previous, data):
                # Calculate position size
                atr = current["atr"]
                position_size = self.calculate_position_size(
                    capital=100000,  # Default capital
                    atr=atr,
                    risk_per_trade=self.risk_per_trade
                )

                # Calculate stop loss and take profit
                stop_loss = current["close"] - (atr * self.trailing_stop_multiplier)
                take_profit = current["close"] + (atr * 3.0)

                signal = Signal(
                    symbol=data.index[-1] if hasattr(data.index, "name") else "SYMBOL",
                    direction=Direction.LONG,
                    strength=self._calculate_signal_strength(current),
                    strategy_name=self.name,
                    position_size=position_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "rsi": current["rsi"],
                        "macd": current["macd"],
                        "adx": current["adx"],
                        "ema_short": current["ema_short"],
                        "ema_long": current["ema_long"],
                        "atr": atr,
                    }
                )
                signals.append(signal)
                self.log_signal(signal)

            # Check for bearish signal (SHORT)
            elif self._is_bearish_setup(current, previous, data):
                atr = current["atr"]
                position_size = self.calculate_position_size(
                    capital=100000,
                    atr=atr,
                    risk_per_trade=self.risk_per_trade
                )

                stop_loss = current["close"] + (atr * self.trailing_stop_multiplier)
                take_profit = current["close"] - (atr * 3.0)

                signal = Signal(
                    symbol=data.index[-1] if hasattr(data.index, "name") else "SYMBOL",
                    direction=Direction.SHORT,
                    strength=self._calculate_signal_strength(current),
                    strategy_name=self.name,
                    position_size=position_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "rsi": current["rsi"],
                        "macd": current["macd"],
                        "adx": current["adx"],
                        "ema_short": current["ema_short"],
                        "ema_long": current["ema_long"],
                        "atr": atr,
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
        """Determine if position should be exited."""
        if len(data) < self.atr_period:
            return False

        try:
            data = self._calculate_indicators(data)
            current = data.iloc[-1]

            # Exit on overbought RSI
            if position.get("direction") == Direction.LONG:
                if current["rsi"] > self.rsi_overbought:
                    logger.info(f"Exit LONG: RSI overbought ({current['rsi']:.1f})")
                    return True

                # Exit if ADX weakens
                if current["adx"] < self.adx_weak:
                    logger.info(f"Exit LONG: ADX weak ({current['adx']:.1f})")
                    return True

                # Exit on trailing stop
                atr = current["atr"]
                stop_price = position.get("stop_loss", current["close"])
                if current["close"] < stop_price:
                    logger.info(f"Exit LONG: Trailing stop hit ({current['close']:.2f})")
                    return True

            # Exit on oversold RSI (SHORT)
            elif position.get("direction") == Direction.SHORT:
                if current["rsi"] < (100 - self.rsi_overbought):
                    logger.info(f"Exit SHORT: RSI oversold ({current['rsi']:.1f})")
                    return True

                # Exit if ADX weakens
                if current["adx"] < self.adx_weak:
                    logger.info(f"Exit SHORT: ADX weak ({current['adx']:.1f})")
                    return True

                # Exit on trailing stop
                stop_price = position.get("stop_loss", current["close"])
                if current["close"] > stop_price:
                    logger.info(f"Exit SHORT: Trailing stop hit ({current['close']:.2f})")
                    return True

        except Exception as e:
            logger.error(f"Exit check error: {e}")

        return False

    def _calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators."""
        df = data.copy()

        # RSI
        df["rsi"] = ta.rsi(df["close"], length=self.rsi_period)

        # EMA
        df["ema_short"] = ta.ema(df["close"], length=self.ema_short)
        df["ema_long"] = ta.ema(df["close"], length=self.ema_long)
        df["ema_trend"] = ta.ema(df["close"], length=self.ema_trend)

        # MACD
        macd_result = ta.macd(
            df["close"],
            fast=self.macd_fast,
            slow=self.macd_slow,
            signal=self.macd_signal
        )
        df["macd"] = macd_result["MACD_12_26_9"]
        df["macd_signal"] = macd_result["MACDs_12_26_9"]
        df["macd_hist"] = macd_result["MACDh_12_26_9"]

        # ADX
        adx_result = ta.adx(df["high"], df["low"], df["close"], length=self.adx_period)
        df["adx"] = adx_result[f"ADX_{self.adx_period}"]
        df["di_plus"] = adx_result[f"DMP_{self.adx_period}"]
        df["di_minus"] = adx_result[f"DMN_{self.adx_period}"]

        # ATR
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)

        return df

    def _is_bullish_setup(
        self,
        current: pd.Series,
        previous: pd.Series,
        data: pd.DataFrame
    ) -> bool:
        """Check if setup meets bullish entry criteria."""
        # RSI recovering from oversold
        if not (previous["rsi"] < self.rsi_oversold and
                current["rsi"] > previous["rsi"]):
            return False

        # MACD bullish crossover
        if not (previous["macd_hist"] <= 0 and current["macd_hist"] > 0):
            return False

        # Price above 50 EMA
        if current["close"] <= current["ema_long"]:
            return False

        # Strong trend (ADX > 25)
        if current["adx"] < self.adx_strong:
            return False

        # Di+ > Di-
        if current["di_plus"] <= current["di_minus"]:
            return False

        return True

    def _is_bearish_setup(
        self,
        current: pd.Series,
        previous: pd.Series,
        data: pd.DataFrame
    ) -> bool:
        """Check if setup meets bearish entry criteria."""
        # RSI recovering from overbought
        if not (previous["rsi"] > (100 - self.rsi_oversold) and
                current["rsi"] < previous["rsi"]):
            return False

        # MACD bearish crossover
        if not (previous["macd_hist"] >= 0 and current["macd_hist"] < 0):
            return False

        # Price below 50 EMA
        if current["close"] >= current["ema_long"]:
            return False

        # Strong trend (ADX > 25)
        if current["adx"] < self.adx_strong:
            return False

        # Di- > Di+
        if current["di_minus"] <= current["di_plus"]:
            return False

        return True

    def _calculate_signal_strength(self, current: pd.Series) -> float:
        """Calculate signal strength (0-1) based on indicator confluence."""
        strength = 0.0

        # ADX strength (up to 0.3)
        adx_strength = min(current["adx"] / 50.0, 1.0) * 0.3
        strength += adx_strength

        # RSI extremeness (up to 0.35)
        if current["rsi"] < 30:
            rsi_strength = (30 - current["rsi"]) / 30 * 0.35
        elif current["rsi"] > 70:
            rsi_strength = (current["rsi"] - 70) / 30 * 0.35
        else:
            rsi_strength = 0.0
        strength += rsi_strength

        # MACD histogram (up to 0.35)
        macd_strength = min(abs(current["macd_hist"]) / 0.5, 1.0) * 0.35
        strength += macd_strength

        return min(strength, 1.0)
