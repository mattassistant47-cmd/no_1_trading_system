"""
Options Wheel strategy for IBKR.
Sells cash-secured puts on quality stocks, upgrades to covered calls when assigned.
Focuses on premium collection and steady income generation.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd
import numpy as np
from loguru import logger

from .base import BaseStrategy, Signal, Direction


class OptionType(str, Enum):
    """Option type enumeration."""
    CALL = "CALL"
    PUT = "PUT"


class WheelPhase(str, Enum):
    """Wheel strategy phase."""
    SELLING_PUTS = "SELLING_PUTS"
    SELLING_CALLS = "SELLING_CALLS"
    ASSIGNED = "ASSIGNED"


@dataclass
class OptionPosition:
    """Options position tracking."""
    symbol: str
    option_type: OptionType
    strike: float
    expiration: datetime
    delta: float
    iv_rank: float
    premium: float
    contracts: int
    entry_date: datetime = None
    exit_date: datetime = None
    pnl: float = 0.0


class OptionsWheel(BaseStrategy):
    """
    Systematic options wheel strategy for high-quality stocks.

    Phase 1: Selling Cash-Secured Puts
    - Sell puts on SPY, QQQ, AAPL, MSFT
    - Delta target: -0.3 (30 delta)
    - DTE target: 30-45 days
    - Sell when IV rank > 30% (higher premium)

    Phase 2: Assignment & Covered Calls
    - If assigned, sell covered calls
    - Delta target: 0.3 (positive 30 delta)
    - Collect premium, manage shares

    Focus: Premium collection and consistent income
    Risk: Capped at strike price for puts, equity risk for calls
    """

    # High-quality underlying stocks
    ELIGIBLE_UNDERLYINGS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "NVDA"]

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        # Options parameters
        self.target_delta_puts = self.config.get("target_delta_puts", 0.3)  # OTM
        self.target_delta_calls = self.config.get("target_delta_calls", 0.3)  # OTM
        self.target_dte_min = self.config.get("target_dte_min", 30)
        self.target_dte_max = self.config.get("target_dte_max", 45)
        self.iv_rank_threshold = self.config.get("iv_rank_threshold", 0.3)  # 30%

        # Position management
        self.max_contracts_per_position = self.config.get("max_contracts_per_position", 5)
        self.min_premium_per_contract = self.config.get("min_premium_per_contract", 50)  # $50
        self.annual_return_target = self.config.get("annual_return_target", 0.25)  # 25%

        # Risk management
        self.max_buying_power_percent = self.config.get("max_buying_power_percent", 0.3)

        # Position tracking
        self.open_positions: Dict[str, OptionPosition] = {}
        self.closed_positions: List[OptionPosition] = []
        self.assigned_shares: Dict[str, int] = {}

        self._asset_class = "options"
        self._timeframe = "1D"

    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """Generate options wheel signals."""
        signals = []

        try:
            # Identify which phase we're in
            for symbol in self.ELIGIBLE_UNDERLYINGS:
                current_price = self._get_symbol_price(data, symbol)
                if current_price is None:
                    continue

                iv_rank = self._get_iv_rank(symbol)
                dte = self._days_to_expiration()

                # Phase 1: Selling puts if we don't own shares
                if symbol not in self.assigned_shares:
                    if iv_rank > self.iv_rank_threshold:
                        # Good premium environment
                        put_strike, put_premium = self._find_option_strike(
                            symbol=symbol,
                            option_type=OptionType.PUT,
                            current_price=current_price,
                            target_delta=self.target_delta_puts,
                            dte=dte
                        )

                        if (put_strike and put_premium and
                            put_premium >= self.min_premium_per_contract and
                            dte >= self.target_dte_min):

                            contracts = self._calculate_contracts(
                                symbol=symbol,
                                strike=put_strike,
                                premium=put_premium
                            )

                            if contracts > 0:
                                signal = Signal(
                                    symbol=symbol,
                                    direction=Direction.LONG,  # Long = sell to open
                                    strength=self._calculate_option_strength(
                                        iv_rank, put_premium, dte
                                    ),
                                    strategy_name=self.name,
                                    metadata={
                                        "action": "SELL_PUT",
                                        "strike": put_strike,
                                        "premium": put_premium,
                                        "delta": -self.target_delta_puts,
                                        "dte": dte,
                                        "iv_rank": iv_rank,
                                        "contracts": contracts,
                                        "collateral_required": put_strike * 100 * contracts,
                                    }
                                )
                                signals.append(signal)
                                self.log_signal(signal)

                # Phase 2: Selling calls if assigned (own shares)
                elif symbol in self.assigned_shares:
                    shares = self.assigned_shares[symbol]

                    call_strike, call_premium = self._find_option_strike(
                        symbol=symbol,
                        option_type=OptionType.CALL,
                        current_price=current_price,
                        target_delta=self.target_delta_calls,
                        dte=dte
                    )

                    if (call_strike and call_premium and
                        call_premium >= self.min_premium_per_contract and
                        dte >= self.target_dte_min):

                        contracts = min(shares // 100, self.max_contracts_per_position)

                        if contracts > 0:
                            signal = Signal(
                                symbol=symbol,
                                direction=Direction.SHORT,  # Short = sell to open
                                strength=self._calculate_option_strength(
                                    iv_rank, call_premium, dte
                                ),
                                strategy_name=self.name,
                                metadata={
                                    "action": "SELL_CALL",
                                    "strike": call_strike,
                                    "premium": call_premium,
                                    "delta": self.target_delta_calls,
                                    "dte": dte,
                                    "iv_rank": iv_rank,
                                    "contracts": contracts,
                                    "shares_covered": contracts * 100,
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
        """Options exit rules."""
        try:
            # Close position if:
            # 1. Profit target hit (50% of max profit for spreads)
            if position.get("pnl", 0) > 0:
                max_profit = position.get("max_profit", position.get("premium", 0))
                if position["pnl"] > max_profit * 0.5:
                    logger.info(f"Exit: Profit target hit ({position['pnl']:.2f})")
                    return True

            # 2. Days to expiration <= 0 (automatic at expiration)
            dte = (position.get("expiration") - datetime.now()).days
            if dte <= 0:
                logger.info("Exit: Expiration reached")
                return True

            # 3. Loss exceeds stop loss (typically at strike for puts)
            if position.get("pnl", 0) < position.get("stop_loss", -9999):
                logger.info(f"Exit: Stop loss hit ({position['pnl']:.2f})")
                return True

        except Exception as e:
            logger.error(f"Exit check error: {e}")

        return False

    def process_assignment(
        self,
        symbol: str,
        strike: float,
        contracts: int
    ) -> None:
        """
        Process put assignment (receiving shares).
        Transitions from phase 1 to phase 2.
        """
        shares = contracts * 100
        self.assigned_shares[symbol] = shares
        logger.info(
            f"Put assigned: {symbol} {shares} shares @ ${strike}"
        )

    def record_covered_call_exit(
        self,
        symbol: str,
        premium: float,
        contracts: int
    ) -> None:
        """Record covered call exit (shares called away)."""
        if symbol in self.assigned_shares:
            shares = self.assigned_shares[symbol]
            del self.assigned_shares[symbol]
            logger.info(
                f"Shares called away: {symbol} {shares} shares, "
                f"premium: ${premium * 100 * contracts:,.0f}"
            )

    def _find_option_strike(
        self,
        symbol: str,
        option_type: OptionType,
        current_price: float,
        target_delta: float,
        dte: int
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Find option strike matching delta target.
        In production, would query live option chain from IBKR.
        """
        # Placeholder - would fetch real option chain
        if option_type == OptionType.PUT:
            strike = current_price * 0.95  # 5% OTM put
            premium = current_price * 0.02  # 2% premium estimate
        else:  # CALL
            strike = current_price * 1.05  # 5% OTM call
            premium = current_price * 0.02

        return strike, premium

    def _get_symbol_price(
        self,
        data: pd.DataFrame,
        symbol: str
    ) -> Optional[float]:
        """Get current price for symbol."""
        if data.empty:
            return None

        return data["close"].iloc[-1]

    def _get_iv_rank(self, symbol: str) -> float:
        """
        Get IV rank (0-1) for symbol.
        In production, would fetch from market data provider.
        """
        # Placeholder - would fetch real IV rank
        return 0.5

    def _days_to_expiration(self, expiration: datetime = None) -> int:
        """Calculate days to expiration."""
        if expiration is None:
            # Default: first Friday after 2 weeks
            today = datetime.now()
            expiration = today + timedelta(days=30)

        return (expiration - datetime.now()).days

    def _calculate_contracts(
        self,
        symbol: str,
        strike: float,
        premium: float
    ) -> int:
        """Calculate number of contracts to sell."""
        # Simple approach: sell 1-5 contracts based on capital
        annual_premium = premium * 100 * 365 / 30  # Annualize
        if annual_premium > 1000:  # Good annual return
            return min(5, self.max_contracts_per_position)
        elif annual_premium > 500:
            return min(3, self.max_contracts_per_position)
        else:
            return 1

    def _calculate_option_strength(
        self,
        iv_rank: float,
        premium: float,
        dte: int
    ) -> float:
        """Calculate signal strength for options trade."""
        strength = 0.0

        # IV rank strength (up to 0.4)
        iv_strength = (iv_rank - 0.3) / 0.7 * 0.4 if iv_rank > 0.3 else 0.0
        strength += min(iv_strength, 0.4)

        # Premium strength (up to 0.3)
        premium_strength = min(premium / 0.03, 1.0) * 0.3
        strength += premium_strength

        # DTE strength - optimal between 30-45 days (up to 0.3)
        if self.target_dte_min <= dte <= self.target_dte_max:
            dte_strength = 0.3
        elif dte < self.target_dte_min:
            dte_strength = (dte / self.target_dte_min) * 0.3
        else:
            dte_strength = max(0.0, (self.target_dte_max / dte) * 0.3)
        strength += dte_strength

        return min(strength, 1.0)

    def get_portfolio_statistics(self) -> Dict[str, Any]:
        """Get portfolio-wide wheel strategy statistics."""
        return {
            "open_positions": len(self.open_positions),
            "assigned_stocks": {s: q for s, q in self.assigned_shares.items()},
            "closed_trades": len(self.closed_positions),
            "total_premium_collected": sum(p.premium for p in self.closed_positions),
            "average_premium_per_contract": (
                sum(p.premium for p in self.closed_positions) / len(self.closed_positions)
                if self.closed_positions else 0
            ),
        }
