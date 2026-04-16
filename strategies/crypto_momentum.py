"""
Crypto-focused momentum strategy with volume weighting and arbitrage detection.
Operates 24/7 with different parameters for different trading sessions.
"""

from typing import List, Dict, Any, Optional
import pandas as pd
import strategies.indicators as ta
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

from .base import BaseStrategy, Signal, Direction


class CryptoMomentum(BaseStrategy):
    """
    Trend following strategy for liquid cryptocurrencies.

    Features:
    - Volume-weighted momentum scoring
    - Cross-exchange arbitrage detection
    - BTC dominance filter (rotate to alts when dominance falls)
    - Configurable parameters for different trading sessions
    - Targets: BTC, ETH, SOL, AVAX, LINK on Alpaca Crypto

    Entry:
    - Volume-weighted momentum positive
    - Price above 50-period EMA
    - Session-appropriate momentum threshold

    Exit:
    - Momentum reversal
    - Stop loss: 2 ATR
    """

    # Supported crypto assets on Alpaca
    CRYPTO_ASSETS = ["BTC", "ETH", "SOL", "AVAX", "LINK"]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        # Strategy parameters
        self.momentum_period = self.config.get("momentum_period", 10)
        self.volume_lookback = self.config.get("volume_lookback", 20)
        self.ema_short = self.config.get("ema_short", 12)
        self.ema_long = self.config.get("ema_long", 50)
        self.atr_period = self.config.get("atr_period", 14)

        # Session-specific thresholds
        self.asian_session_threshold = self.config.get("asian_session_threshold", 0.3)
        self.european_session_threshold = self.config.get("european_session_threshold", 0.4)
        self.us_session_threshold = self.config.get("us_session_threshold", 0.5)

        # Arbitrage and BTC dominance
        self.arb_threshold = self.config.get("arb_threshold", 0.02)  # 2%
        self.btc_dominance_threshold = self.config.get("btc_dominance_threshold", 0.45)
        self.min_volume_usd = self.config.get("min_volume_usd", 1000000)  # $1M+

        self.risk_per_trade = self.config.get("risk_per_trade", 0.02)
        self.trailing_stop_multiplier = self.config.get("trailing_stop_multiplier", 2.0)

        self._asset_class = "crypto"
        self._timeframe = "4H"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate crypto momentum signals."""
        signals = []

        if len(data) < max(self.ema_long, self.volume_lookback):
            return signals

        try:
            # Calculate indicators
            data = self._calculate_indicators(data)

            # Get BTC dominance for filtering
            btc_dominance = self._get_btc_dominance()
            session_type = self._get_trading_session()
            threshold = self._get_session_threshold(session_type)

            current = data.iloc[-1]
            previous = data.iloc[-2] if len(data) > 1 else current

            # Check volume threshold
            if current["volume_usd"] < self.min_volume_usd:
                logger.debug(f"Volume too low: ${current['volume_usd']:,.0f}")
                return signals

            # Volume-weighted momentum
            vwm = current["vwm"]

            # Long signal
            if (vwm > threshold and
                current["close"] > current["ema_long"] and
                previous["vwm"] <= threshold):

                # Apply BTC dominance filter
                if btc_dominance > self.btc_dominance_threshold:
                    # BTC dominant: only trade BTC
                    if not self._is_btc_data(data):
                        logger.debug("BTC dominance high, only trading BTC")
                        return signals

                position_size = self.calculate_position_size(
                    capital=100000,
                    atr=current["atr"],
                    risk_per_trade=self.risk_per_trade
                )

                signal = Signal(
                    symbol=data.index[-1] if hasattr(data.index, "name") else "BTC",
                    direction=Direction.LONG,
                    strength=self._calculate_crypto_strength(current, Direction.LONG),
                    strategy_name=self.name,
                    position_size=position_size,
                    stop_loss=current["close"] - (current["atr"] * self.trailing_stop_multiplier),
                    take_profit=current["close"] + (current["atr"] * 3.0),
                    metadata={
                        "vwm": vwm,
                        "ema_short": current["ema_short"],
                        "ema_long": current["ema_long"],
                        "atr": current["atr"],
                        "volume_usd": current["volume_usd"],
                        "btc_dominance": btc_dominance,
                        "session": session_type,
                    }
                )
                signals.append(signal)
                self.log_signal(signal)

            # Short signal
            elif (vwm < -threshold and
                  current["close"] < current["ema_long"] and
                  previous["vwm"] >= -threshold):

                position_size = self.calculate_position_size(
                    capital=100000,
                    atr=current["atr"],
                    risk_per_trade=self.risk_per_trade
                )

                signal = Signal(
                    symbol=data.index[-1] if hasattr(data.index, "name") else "BTC",
                    direction=Direction.SHORT,
                    strength=self._calculate_crypto_strength(current, Direction.SHORT),
                    strategy_name=self.name,
                    position_size=position_size,
                    stop_loss=current["close"] + (current["atr"] * self.trailing_stop_multiplier),
                    take_profit=current["close"] - (current["atr"] * 3.0),
                    metadata={
                        "vwm": vwm,
                        "ema_short": current["ema_short"],
                        "ema_long": current["ema_long"],
                        "atr": current["atr"],
                        "volume_usd": current["volume_usd"],
                        "btc_dominance": btc_dominance,
                        "session": session_type,
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
        """Determine if crypto position should exit."""
        if len(data) < self.atr_period:
            return False

        try:
            data = self._calculate_indicators(data)
            current = data.iloc[-1]
            previous = data.iloc[-2] if len(data) > 1 else current

            # Exit on VWM reversal
            if position.get("direction") == Direction.LONG:
                if current["vwm"] < 0:
                    logger.info(f"Exit LONG: VWM reversed ({current['vwm']:.3f})")
                    return True

                # Trailing stop
                if current["close"] < position.get("stop_loss", current["close"]):
                    logger.info(f"Exit LONG: Trailing stop ({current['close']:.2f})")
                    return True

            elif position.get("direction") == Direction.SHORT:
                if current["vwm"] > 0:
                    logger.info(f"Exit SHORT: VWM reversed ({current['vwm']:.3f})")
                    return True

                # Trailing stop
                if current["close"] > position.get("stop_loss", current["close"]):
                    logger.info(f"Exit SHORT: Trailing stop ({current['close']:.2f})")
                    return True

        except Exception as e:
            logger.error(f"Exit check error: {e}")

        return False

    def detect_arbitrage(
        self,
        symbol: str,
        alpaca_price: float,
        coingecko_price: float
    ) -> Optional[Dict[str, float]]:
        """
        Detect cross-exchange arbitrage opportunities.

        Args:
            symbol: Crypto symbol (BTC, ETH, etc)
            alpaca_price: Price on Alpaca exchange
            coingecko_price: Price on CoinGecko (market average)

        Returns:
            Dictionary with arbitrage details or None if threshold not met
        """
        if alpaca_price <= 0 or coingecko_price <= 0:
            return None

        price_diff = (alpaca_price - coingecko_price) / coingecko_price
        abs_diff = abs(price_diff)

        if abs_diff > self.arb_threshold:
            arb_info = {
                "symbol": symbol,
                "alpaca_price": alpaca_price,
                "coingecko_price": coingecko_price,
                "price_diff_pct": price_diff * 100,
                "direction": "buy_alpaca" if price_diff < 0 else "sell_alpaca",
            }
            logger.info(f"Arbitrage detected: {symbol} {price_diff:+.2%}")
            return arb_info

        return None

    def _calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate crypto-specific indicators."""
        df = data.copy()

        # Volume in USD (assumes close price * volume = nominal value)
        df["volume_usd"] = df["close"] * df["volume"]

        # EMA
        df["ema_short"] = ta.ema(df["close"], length=self.ema_short)
        df["ema_long"] = ta.ema(df["close"], length=self.ema_long)

        # ATR
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)

        # Volume-weighted momentum
        df["momentum"] = df["close"].diff(self.momentum_period)
        df["avg_volume"] = df["volume"].rolling(self.volume_lookback).mean()
        df["volume_ma_ratio"] = df["volume"] / df["avg_volume"]

        # VWM: momentum weighted by volume ratio
        df["vwm"] = (
            df["momentum"] / df["close"] * df["volume_ma_ratio"]
        ).rolling(5).mean()

        return df

    def _get_trading_session(self) -> str:
        """Determine current trading session."""
        utc_hour = datetime.utcnow().hour

        # Asian session: 0-8 UTC
        if 0 <= utc_hour < 8:
            return "asian"
        # European session: 8-16 UTC
        elif 8 <= utc_hour < 16:
            return "european"
        # US session: 16-24 UTC
        else:
            return "us"

    def _get_session_threshold(self, session: str) -> float:
        """Get momentum threshold for session."""
        thresholds = {
            "asian": self.asian_session_threshold,
            "european": self.european_session_threshold,
            "us": self.us_session_threshold,
        }
        return thresholds.get(session, 0.4)

    def _get_btc_dominance(self) -> float:
        """
        Get current BTC dominance.
        In production, this would fetch from CoinGecko or similar.
        """
        # Placeholder - would be fetched from external API
        return 0.50  # 50% BTC dominance

    def _is_btc_data(self, data: pd.DataFrame) -> bool:
        """Check if data is for BTC."""
        return (hasattr(data.index, "name") and
                data.index.name == "BTC") or "BTC" in str(data.columns)

    def _calculate_crypto_strength(
        self,
        current: pd.Series,
        direction: Direction
    ) -> float:
        """Calculate crypto momentum signal strength."""
        strength = 0.0

        # VWM strength (up to 0.5)
        vwm_strength = min(abs(current["vwm"]) * 2, 1.0) * 0.5
        strength += vwm_strength

        # Trend strength - EMA separation (up to 0.3)
        ema_diff = abs(current["ema_short"] - current["ema_long"]) / current["ema_long"]
        ema_strength = min(ema_diff * 10, 1.0) * 0.3
        strength += ema_strength

        # Volume strength (up to 0.2)
        vol_strength = min(current["volume_ma_ratio"], 2.0) / 2.0 * 0.2
        strength += vol_strength

        return min(strength, 1.0)
