"""
Intelligent Position Sizing Engine

Calculates optimal position sizes using Kelly Criterion, ATR-based sizing,
volatility adjustment, and risk-based limits.
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from enum import Enum
import numpy as np
from loguru import logger


class SizingMethod(str, Enum):
    """Position sizing methods"""
    KELLY_FULL = "kelly_full"
    KELLY_FRACTIONAL = "kelly_fractional"
    ATR_BASED = "atr_based"
    FIXED_RISK = "fixed_risk"
    VOLATILITY_ADJUSTED = "volatility_adjusted"


@dataclass
class SignalMetrics:
    """Signal metrics for sizing"""
    symbol: str
    signal_strength: float  # 0-1
    win_rate: float  # 0-1
    avg_win: float
    avg_loss: float
    volatility: float  # Historical volatility (annualized)
    atr: float  # Average True Range
    current_price: float
    entry_price: float
    stop_loss: float


@dataclass
class SizingResult:
    """Position sizing result"""
    quantity: int
    notional_value: float
    risk_amount: float
    kelly_fraction: Optional[float] = None
    method: Optional[SizingMethod] = None
    rationale: str = ""


class PositionSizer:
    """
    Intelligent position sizing engine supporting multiple strategies.

    Methods:
    - Kelly Criterion (full and fractional)
    - ATR-based sizing (position size inversely proportional to volatility)
    - Fixed risk per trade
    - Volatility-adjusted sizing
    """

    def __init__(
        self,
        kelly_fraction: float = 0.25,  # Use 25% of Kelly
        max_position_size: int = 10000,
        min_position_size: int = 1,
    ):
        """
        Initialize PositionSizer.

        Args:
            kelly_fraction: Fraction of full Kelly to use (0.25 = 1/4 Kelly)
            max_position_size: Maximum position size in units
            min_position_size: Minimum position size in units
        """
        self.kelly_fraction = kelly_fraction
        self.max_position_size = max_position_size
        self.min_position_size = min_position_size

        logger.info(
            f"PositionSizer initialized with "
            f"kelly_fraction={kelly_fraction}, "
            f"max_size={max_position_size}, "
            f"min_size={min_position_size}"
        )

    async def calculate_size(
        self,
        signal: SignalMetrics,
        account_equity: float,
        current_positions: Optional[Dict[str, float]] = None,
        method: SizingMethod = SizingMethod.KELLY_FRACTIONAL,
    ) -> SizingResult:
        """
        Calculate position size for a trade signal.

        Args:
            signal: Signal metrics including win rate, avg win/loss, volatility
            account_equity: Current account equity
            current_positions: Dict of {symbol: quantity} for existing positions
            method: Sizing method to use

        Returns:
            SizingResult with quantity, notional value, and rationale
        """
        current_positions = current_positions or {}

        if method == SizingMethod.KELLY_FULL:
            return await self._kelly_full(signal, account_equity)
        elif method == SizingMethod.KELLY_FRACTIONAL:
            return await self._kelly_fractional(signal, account_equity)
        elif method == SizingMethod.ATR_BASED:
            return await self._atr_based(signal, account_equity)
        elif method == SizingMethod.FIXED_RISK:
            return await self._fixed_risk(signal, account_equity, risk_pct=1.0)
        elif method == SizingMethod.VOLATILITY_ADJUSTED:
            return await self._volatility_adjusted(signal, account_equity)
        else:
            raise ValueError(f"Unknown sizing method: {method}")

    async def _kelly_full(
        self, signal: SignalMetrics, account_equity: float
    ) -> SizingResult:
        """
        Calculate position size using full Kelly Criterion.

        Kelly % = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

        Args:
            signal: Signal metrics
            account_equity: Account equity

        Returns:
            SizingResult
        """
        # Kelly Criterion calculation
        win_rate = signal.win_rate
        avg_win = signal.avg_win
        avg_loss = signal.avg_loss

        if avg_win <= 0 or avg_loss <= 0:
            return SizingResult(
                quantity=0,
                notional_value=0.0,
                risk_amount=0.0,
                method=SizingMethod.KELLY_FULL,
                rationale="Invalid win/loss ratios for Kelly calculation",
            )

        # Kelly formula: f = (p*b - q) / b
        # where: p = win rate, q = 1-p, b = win/loss ratio
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        kelly_pct = (p * b - q) / b if b > 0 else 0.0

        # Ensure kelly_pct is reasonable
        kelly_pct = max(0.0, min(kelly_pct, 0.25))  # Cap at 25%

        kelly_fraction = kelly_pct
        risk_amount = account_equity * kelly_fraction

        quantity = int(risk_amount / signal.current_price)
        quantity = max(self.min_position_size, min(quantity, self.max_position_size))

        notional_value = quantity * signal.current_price

        return SizingResult(
            quantity=quantity,
            notional_value=notional_value,
            risk_amount=risk_amount,
            kelly_fraction=kelly_fraction,
            method=SizingMethod.KELLY_FULL,
            rationale=(
                f"Kelly: {kelly_pct:.1%}, risk: ${risk_amount:.2f}, "
                f"qty: {quantity} @ ${signal.current_price:.2f}"
            ),
        )

    async def _kelly_fractional(
        self, signal: SignalMetrics, account_equity: float
    ) -> SizingResult:
        """
        Calculate position size using fractional Kelly Criterion.

        Uses kelly_fraction of the full Kelly optimal position.

        Args:
            signal: Signal metrics
            account_equity: Account equity

        Returns:
            SizingResult
        """
        # Calculate full Kelly first
        kelly_result = await self._kelly_full(signal, account_equity)

        if kelly_result.kelly_fraction is None:
            return kelly_result

        # Apply fraction
        kelly_pct = kelly_result.kelly_fraction * self.kelly_fraction
        risk_amount = account_equity * kelly_pct

        quantity = int(risk_amount / signal.current_price)
        quantity = max(self.min_position_size, min(quantity, self.max_position_size))

        notional_value = quantity * signal.current_price

        return SizingResult(
            quantity=quantity,
            notional_value=notional_value,
            risk_amount=risk_amount,
            kelly_fraction=kelly_pct,
            method=SizingMethod.KELLY_FRACTIONAL,
            rationale=(
                f"Fractional Kelly ({self.kelly_fraction:.0%}): {kelly_pct:.1%}, "
                f"risk: ${risk_amount:.2f}, qty: {quantity} @ ${signal.current_price:.2f}"
            ),
        )

    async def _atr_based(
        self, signal: SignalMetrics, account_equity: float
    ) -> SizingResult:
        """
        Calculate position size based on ATR (Average True Range).

        Position size inversely proportional to volatility:
        Position Size = (Account * Risk % / ATR)

        Args:
            signal: Signal metrics
            account_equity: Account equity

        Returns:
            SizingResult
        """
        risk_pct = 0.02  # 2% risk per trade
        risk_amount = account_equity * risk_pct

        if signal.atr <= 0:
            return SizingResult(
                quantity=0,
                notional_value=0.0,
                risk_amount=0.0,
                method=SizingMethod.ATR_BASED,
                rationale="Invalid ATR for sizing",
            )

        # Position size = risk amount / ATR
        quantity = int(risk_amount / signal.atr)
        quantity = max(self.min_position_size, min(quantity, self.max_position_size))

        notional_value = quantity * signal.current_price

        return SizingResult(
            quantity=quantity,
            notional_value=notional_value,
            risk_amount=risk_amount,
            method=SizingMethod.ATR_BASED,
            rationale=(
                f"ATR-based: ATR=${signal.atr:.2f}, risk: ${risk_amount:.2f}, "
                f"qty: {quantity} @ ${signal.current_price:.2f}"
            ),
        )

    async def _fixed_risk(
        self, signal: SignalMetrics, account_equity: float, risk_pct: float = 1.0
    ) -> SizingResult:
        """
        Calculate position size based on fixed risk percentage per trade.

        Position Size = (Account Equity * Risk %) / Risk per Unit

        Args:
            signal: Signal metrics
            account_equity: Account equity
            risk_pct: Risk percentage per trade

        Returns:
            SizingResult
        """
        risk_amount = account_equity * (risk_pct / 100)
        risk_per_unit = abs(signal.current_price - signal.stop_loss)

        if risk_per_unit <= 0:
            return SizingResult(
                quantity=0,
                notional_value=0.0,
                risk_amount=0.0,
                method=SizingMethod.FIXED_RISK,
                rationale="Invalid stop loss for sizing",
            )

        quantity = int(risk_amount / risk_per_unit)
        quantity = max(self.min_position_size, min(quantity, self.max_position_size))

        notional_value = quantity * signal.current_price

        return SizingResult(
            quantity=quantity,
            notional_value=notional_value,
            risk_amount=risk_amount,
            method=SizingMethod.FIXED_RISK,
            rationale=(
                f"Fixed risk ({risk_pct}%): ${risk_amount:.2f}, "
                f"qty: {quantity} @ ${signal.current_price:.2f}"
            ),
        )

    async def _volatility_adjusted(
        self, signal: SignalMetrics, account_equity: float
    ) -> SizingResult:
        """
        Calculate position size with volatility adjustment.

        Reduces position size in high-volatility environments.

        Position Size = Base Size * (Target Volatility / Current Volatility)

        Args:
            signal: Signal metrics
            account_equity: Account equity

        Returns:
            SizingResult
        """
        # Base sizing (using fixed risk)
        base_result = await self._fixed_risk(signal, account_equity, risk_pct=2.0)

        if signal.volatility <= 0:
            return base_result

        # Target volatility (e.g., 15% annualized)
        target_volatility = 0.15
        volatility_adjustment = target_volatility / signal.volatility

        # Clip adjustment to reasonable bounds (0.5x to 2.0x)
        volatility_adjustment = max(0.5, min(volatility_adjustment, 2.0))

        adjusted_quantity = int(base_result.quantity * volatility_adjustment)
        adjusted_quantity = max(
            self.min_position_size, min(adjusted_quantity, self.max_position_size)
        )

        adjusted_notional = adjusted_quantity * signal.current_price

        return SizingResult(
            quantity=adjusted_quantity,
            notional_value=adjusted_notional,
            risk_amount=base_result.risk_amount * volatility_adjustment,
            method=SizingMethod.VOLATILITY_ADJUSTED,
            rationale=(
                f"Volatility-adjusted: vol={signal.volatility:.1%}, "
                f"adjustment={volatility_adjustment:.2f}x, "
                f"qty: {adjusted_quantity} @ ${signal.current_price:.2f}"
            ),
        )

    async def calculate_max_position(
        self,
        account_equity: float,
        current_price: float,
        max_position_pct: float = 5.0,
        max_loss_pct: float = 1.0,
        stop_loss: Optional[float] = None,
    ) -> SizingResult:
        """
        Calculate maximum allowed position size given constraints.

        Args:
            account_equity: Account equity
            current_price: Current asset price
            max_position_pct: Maximum position as % of account
            max_loss_pct: Maximum loss as % of account
            stop_loss: Stop loss price (if specified)

        Returns:
            SizingResult with maximum allowed quantity
        """
        # Calculate by position %
        max_by_pct = int((account_equity * max_position_pct / 100) / current_price)

        # Calculate by loss limit
        if stop_loss is not None:
            risk_per_unit = abs(current_price - stop_loss)
            max_by_loss = int((account_equity * max_loss_pct / 100) / risk_per_unit)
        else:
            max_by_loss = self.max_position_size

        # Take the minimum
        quantity = min(max_by_pct, max_by_loss, self.max_position_size)
        quantity = max(self.min_position_size, quantity)

        notional_value = quantity * current_price
        risk_amount = account_equity * max_loss_pct / 100

        return SizingResult(
            quantity=quantity,
            notional_value=notional_value,
            risk_amount=risk_amount,
            method=None,
            rationale=(
                f"Max position: {quantity} shares "
                f"({notional_value / account_equity:.1%} of account)"
            ),
        )

    def _validate_signal(self, signal: SignalMetrics) -> bool:
        """Validate signal metrics"""
        if signal.win_rate < 0 or signal.win_rate > 1:
            logger.warning(f"Invalid win_rate: {signal.win_rate}")
            return False

        if signal.current_price <= 0:
            logger.warning(f"Invalid current_price: {signal.current_price}")
            return False

        return True
