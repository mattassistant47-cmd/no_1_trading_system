"""
Base strategy class with signal generation, backtesting, and performance tracking.
All strategies inherit from BaseStrategy and implement required methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np
import pandas as pd
from loguru import logger

import sys

logger.remove()
logger.add(
    sys.stderr,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="INFO",
)


class Direction(str, Enum):
    """Signal direction enumeration."""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    EXIT = "EXIT"


@dataclass
class Signal:
    """
    Trading signal dataclass.
    Represents a single trading opportunity with metadata.
    """
    symbol: str
    direction: Direction
    strength: float  # 0.0 to 1.0, confidence level
    strategy_name: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    position_size: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    def __post_init__(self):
        """Validate signal parameters."""
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"Signal strength must be 0-1, got {self.strength}")
        if self.direction not in Direction:
            raise ValueError(f"Invalid direction: {self.direction}")

    def __repr__(self) -> str:
        return (
            f"Signal({self.symbol} {self.direction.value} "
            f"strength={self.strength:.2f} from {self.strategy_name})"
        )


@dataclass
class PerformanceMetrics:
    """Performance tracking dataclass."""
    win_rate: float = 0.0
    loss_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_return: float = 0.0
    cumulative_pnl: float = 0.0
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Provides signal generation, backtesting, and performance tracking.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize strategy with configuration.

        Args:
            config: Strategy-specific configuration dictionary
        """
        self.config = config or {}
        self._name = self.__class__.__name__
        self._description = self.__doc__ or "No description"
        self._asset_class = self.config.get("asset_class", "equities")
        self._timeframe = self.config.get("timeframe", "1D")
        self._enabled = self.config.get("enabled", True)
        self._weight = self.config.get("weight", 1.0)

        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.signals_generated: List[Signal] = []
        self.trades_closed: List[Dict[str, Any]] = []

        logger.info(f"Initialized {self._name} strategy")

    @property
    def name(self) -> str:
        """Strategy name."""
        return self._name

    @property
    def description(self) -> str:
        """Strategy description."""
        return self._description

    @property
    def asset_class(self) -> str:
        """Target asset class (equities, crypto, options, etc)."""
        return self._asset_class

    @property
    def timeframe(self) -> str:
        """Candle timeframe (1H, 4H, 1D, etc)."""
        return self._timeframe

    @property
    def enabled(self) -> bool:
        """Whether strategy is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable/disable strategy."""
        self._enabled = value
        logger.info(f"{self._name} enabled={value}")

    @property
    def weight(self) -> float:
        """Strategy weight in ensemble (0.0 to 1.0)."""
        return self._weight

    @weight.setter
    def weight(self, value: float) -> None:
        """Set strategy weight."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Weight must be 0-1, got {value}")
        self._weight = value

    @abstractmethod
    def generate_signals(
        self, data: pd.DataFrame
    ) -> List[Signal]:
        """
        Generate trading signals from market data.

        Args:
            data: OHLCV dataframe with columns [open, high, low, close, volume]

        Returns:
            List of Signal objects representing trading opportunities
        """
        pass

    @abstractmethod
    def should_exit(
        self,
        position: Dict[str, Any],
        data: pd.DataFrame
    ) -> bool:
        """
        Determine if an open position should be exited.

        Args:
            position: Dictionary with position details (symbol, entry_price, etc)
            data: Current market data

        Returns:
            True if position should be exited
        """
        pass

    def calculate_position_size(
        self,
        capital: float,
        atr: float,
        risk_per_trade: float = 0.02
    ) -> float:
        """
        Calculate position size based on ATR and risk parameters.

        Args:
            capital: Available trading capital
            atr: Average True Range (price points)
            risk_per_trade: Risk as % of capital per trade (default 2%)

        Returns:
            Position size in shares
        """
        if atr <= 0:
            return 0.0

        risk_amount = capital * risk_per_trade
        position_size = risk_amount / atr
        return max(0.0, position_size)

    def backtest(
        self,
        data: pd.DataFrame,
        initial_capital: float = 100000.0,
        commission: float = 0.001
    ) -> Dict[str, Any]:
        """
        Walk-forward backtest of strategy.

        Args:
            data: OHLCV dataframe
            initial_capital: Starting capital
            commission: Trading commission as decimal (0.1%)

        Returns:
            Dictionary with backtest results and metrics
        """
        logger.info(
            f"Starting backtest for {self._name} "
            f"on {len(data)} bars, ${initial_capital:,.0f}"
        )

        if data.empty:
            logger.warning("Empty dataframe provided to backtest")
            return {"error": "Empty dataframe"}

        if not all(col in data.columns for col in ["open", "high", "low", "close", "volume"]):
            logger.warning("Missing OHLCV columns in backtest data")
            return {"error": "Missing OHLCV columns"}

        capital = initial_capital
        position = None
        entry_price = None
        trades = []
        equity_curve = [capital]
        returns = []

        try:
            for i in range(len(data)):
                current_data = data.iloc[:i + 1]
                current_price = data["close"].iloc[i]

                # Generate signals for current bar
                signals = self.generate_signals(current_data)

                # Entry logic
                if position is None and signals:
                    signal = signals[0]
                    if signal.direction in [Direction.LONG, Direction.SHORT]:
                        position = {
                            "symbol": signal.symbol,
                            "direction": signal.direction,
                            "entry_price": current_price,
                            "entry_idx": i,
                            "size": signal.position_size or 1.0,
                        }
                        cost = position["size"] * current_price * (1 + commission)
                        capital -= cost
                        logger.debug(
                            f"Entry {signal.direction.value} "
                            f"@ {current_price:.2f} ({position['size']:.2f} shares)"
                        )

                # Exit logic
                if position is not None:
                    if self.should_exit(position, current_data):
                        exit_price = current_price
                        pnl = position["size"] * (
                            exit_price - position["entry_price"]
                        )
                        if position["direction"] == Direction.SHORT:
                            pnl = -pnl

                        proceeds = position["size"] * exit_price * (1 - commission)
                        capital += proceeds

                        trade = {
                            "entry_price": position["entry_price"],
                            "exit_price": exit_price,
                            "pnl": pnl,
                            "return": pnl / (position["size"] * position["entry_price"]),
                            "bars_held": i - position["entry_idx"],
                        }
                        trades.append(trade)
                        logger.debug(f"Exit @ {exit_price:.2f}, PnL: ${pnl:.2f}")
                        position = None

                # Update equity curve
                if position is not None:
                    position_value = position["size"] * current_price
                    total_equity = capital + position_value
                else:
                    total_equity = capital

                equity_curve.append(total_equity)
                period_return = (
                    (total_equity - equity_curve[-2]) / equity_curve[-2]
                    if len(equity_curve) > 1
                    else 0.0
                )
                returns.append(period_return)

            # Calculate metrics
            equity_array = np.array(equity_curve)
            returns_array = np.array(returns)

            total_return = (equity_curve[-1] - initial_capital) / initial_capital
            max_dd = self._calculate_max_drawdown(equity_array)
            sharpe = self._calculate_sharpe_ratio(returns_array)

            if trades:
                wins = [t for t in trades if t["pnl"] > 0]
                losses = [t for t in trades if t["pnl"] < 0]
                self.metrics.winning_trades = len(wins)
                self.metrics.losing_trades = len(losses)
                self.metrics.win_rate = len(wins) / len(trades) if trades else 0.0
                self.metrics.avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0.0
                self.metrics.avg_loss = np.mean([t["pnl"] for t in losses]) if losses else 0.0
                self.metrics.profit_factor = (
                    sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses))
                    if losses else 0.0
                )

            self.metrics.trade_count = len(trades)
            self.metrics.total_return = total_return
            self.metrics.max_drawdown = max_dd
            self.metrics.sharpe_ratio = sharpe
            self.metrics.cumulative_pnl = equity_curve[-1] - initial_capital

            results = {
                "initial_capital": initial_capital,
                "final_capital": equity_curve[-1],
                "total_return": total_return,
                "max_drawdown": max_dd,
                "sharpe_ratio": sharpe,
                "trade_count": len(trades),
                "winning_trades": self.metrics.winning_trades,
                "win_rate": self.metrics.win_rate,
                "avg_win": self.metrics.avg_win,
                "avg_loss": self.metrics.avg_loss,
                "profit_factor": self.metrics.profit_factor,
                "trades": trades,
                "equity_curve": equity_curve,
            }

            logger.info(
                f"Backtest complete: ${equity_curve[-1]:,.0f} "
                f"({total_return:+.1%}), Sharpe={sharpe:.2f}, "
                f"DD={max_dd:.1%}, Win%={self.metrics.win_rate:.1%}"
            )

            return results

        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            return {"error": str(e)}

    @staticmethod
    def _calculate_max_drawdown(equity_curve: np.ndarray) -> float:
        """Calculate maximum drawdown from equity curve."""
        cummax = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - cummax) / cummax
        return np.min(drawdown)

    @staticmethod
    def _calculate_sharpe_ratio(
        returns: np.ndarray,
        risk_free_rate: float = 0.04
    ) -> float:
        """Calculate Sharpe ratio (annualized, 252 trading days)."""
        if len(returns) < 2:
            return 0.0

        excess_returns = returns - (risk_free_rate / 252)
        std = np.std(excess_returns)
        if std == 0:
            return 0.0

        return np.mean(excess_returns) / std * np.sqrt(252)

    def get_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset performance metrics."""
        self.metrics = PerformanceMetrics()
        self.signals_generated.clear()
        self.trades_closed.clear()
        logger.info(f"Metrics reset for {self._name}")

    def log_signal(self, signal: Signal) -> None:
        """Log a generated signal."""
        self.signals_generated.append(signal)
        logger.info(f"Signal: {signal}")

    def log_trade_closed(self, trade: Dict[str, Any]) -> None:
        """Log a closed trade."""
        self.trades_closed.append(trade)
        logger.info(f"Trade closed: {trade}")
