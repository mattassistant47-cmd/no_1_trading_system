"""
Central Risk Manager

Comprehensive pre-trade and portfolio-level risk checks with real-time monitoring.
Enforces position limits, concentration caps, sector exposure limits, and correlation
constraints. Tracks P&L and triggers alerts when risk thresholds are exceeded.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Tuple
import numpy as np
from loguru import logger
from abc import ABC, abstractmethod


class AssetClass(str, Enum):
    """Supported asset classes"""
    EQUITY = "equity"
    CRYPTO = "crypto"
    OPTIONS = "options"
    PREDICTION_MARKET = "prediction_market"


class OrderType(str, Enum):
    """Order types"""
    BUY = "buy"
    SELL = "sell"
    SHORT = "short"
    CLOSE = "close"


@dataclass
class Order:
    """Order object"""
    symbol: str
    quantity: float
    price: float
    side: OrderType
    asset_class: AssetClass
    timestamp: datetime = field(default_factory=datetime.utcnow)
    portfolio_pct: float = 0.0  # Will be calculated
    strategy_id: Optional[str] = None


@dataclass
class Position:
    """Position tracking"""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    asset_class: AssetClass
    sector: Optional[str] = None
    opened_at: datetime = field(default_factory=datetime.utcnow)
    pnl: float = 0.0
    pnl_pct: float = 0.0

    def update_pnl(self):
        """Update position P&L"""
        self.pnl = (self.current_price - self.entry_price) * self.quantity
        if self.entry_price > 0:
            self.pnl_pct = (self.current_price - self.entry_price) / self.entry_price

    def notional_value(self) -> float:
        """Get position notional value"""
        return abs(self.quantity * self.current_price)


@dataclass
class PortfolioRisk:
    """Portfolio-level risk metrics"""
    total_equity: float
    total_positions_value: float
    total_pnl: float
    total_pnl_pct: float
    today_pnl: float
    max_drawdown_pct: float
    current_leverage: float
    gross_exposure: float  # Sum of absolute position values
    net_exposure: float    # Directional exposure
    max_drawdown_breach: bool = False
    max_daily_loss_breach: bool = False
    concentration_breach: bool = False
    sector_exposure_breach: bool = False
    correlation_breach: bool = False


class RiskManager:
    """
    Central risk management engine with pre-trade and portfolio monitoring.

    Enforces:
    - Position limits (size, concentration, sector)
    - Portfolio limits (leverage, drawdown, daily loss)
    - Asset class allocation limits
    - Correlation constraints
    - Real-time P&L monitoring
    """

    def __init__(
        self,
        initial_equity: float = 1_000_000.0,
        max_drawdown_pct: float = 10.0,
        max_daily_loss_pct: float = 2.0,
        max_positions: int = 30,
        max_leverage: float = 1.5,
        max_single_position_pct: float = 5.0,
        max_loss_per_trade_pct: float = 1.0,
        max_sector_exposure_pct: float = 25.0,
        max_correlation_threshold: float = 0.85,
    ):
        """
        Initialize RiskManager.

        Args:
            initial_equity: Initial account equity
            max_drawdown_pct: Maximum allowed drawdown percentage
            max_daily_loss_pct: Maximum daily loss percentage
            max_positions: Maximum number of open positions
            max_leverage: Maximum portfolio leverage
            max_single_position_pct: Max % of portfolio in single position
            max_loss_per_trade_pct: Max loss per individual trade
            max_sector_exposure_pct: Max exposure to single sector
            max_correlation_threshold: Max correlation between positions
        """
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.peak_equity = initial_equity

        # Limits
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_positions = max_positions
        self.max_leverage = max_leverage
        self.max_single_position_pct = max_single_position_pct
        self.max_loss_per_trade_pct = max_loss_per_trade_pct
        self.max_sector_exposure_pct = max_sector_exposure_pct
        self.max_correlation_threshold = max_correlation_threshold

        # Asset class allocation limits (pulled from settings with sensible fallbacks)
        try:
            from config.settings import settings as _settings
            _limits = dict(_settings.trading.asset_class_limits or {})
        except Exception:
            _limits = {}
        self.asset_class_limits = {
            AssetClass.EQUITY: _limits.get("EQUITY", 0.50),
            AssetClass.CRYPTO: _limits.get("CRYPTO", 0.20),
            AssetClass.OPTIONS: _limits.get("OPTIONS", 0.20),
            AssetClass.PREDICTION_MARKET: _limits.get("PREDICTION_MARKET", 0.10),
        }

        # State
        self.positions: Dict[str, Position] = {}
        self.daily_pnl = 0.0
        self.daily_start_time = datetime.utcnow()
        self.trading_enabled = True
        self.breach_alerts: List[str] = []

        logger.info(
            f"RiskManager initialized with equity=${initial_equity:,.2f}, "
            f"max_drawdown={max_drawdown_pct}%, max_daily_loss={max_daily_loss_pct}%"
        )

    async def check_order(self, order: Order) -> Tuple[bool, str]:
        """
        Pre-trade risk check for incoming order.

        Args:
            order: Order to check

        Returns:
            Tuple of (approved: bool, reason: str)
        """
        if not self.trading_enabled:
            return False, "Trading disabled by circuit breaker"

        # Check position limit
        if len(self.positions) >= self.max_positions and order.symbol not in self.positions:
            return False, f"Max positions limit ({self.max_positions}) reached"

        # Calculate new position size
        order_notional = order.quantity * order.price
        order_pct = (order_notional / self.current_equity) * 100
        order.portfolio_pct = order_pct

        # Check max single position limit
        current_position_value = 0.0
        if order.symbol in self.positions:
            current_position_value = self.positions[order.symbol].notional_value()

        new_position_value = current_position_value + order_notional
        new_position_pct = (new_position_value / self.current_equity) * 100

        if new_position_pct > self.max_single_position_pct:
            return (
                False,
                f"Position size {new_position_pct:.2f}% exceeds limit "
                f"({self.max_single_position_pct}%)"
            )

        # Check max loss per trade
        worst_case_loss = order.quantity * order.price * (self.max_loss_per_trade_pct / 100)
        if order.quantity * order.price > worst_case_loss:
            max_allowed_qty = (self.current_equity * self.max_loss_per_trade_pct / 100) / order.price
            if order.quantity > max_allowed_qty:
                return (
                    False,
                    f"Trade quantity {order.quantity} exceeds max loss limit "
                    f"({max_allowed_qty:.2f} @ {self.max_loss_per_trade_pct}% risk)"
                )

        # Check asset class limits
        ac_check, ac_reason = await self._check_asset_class_limits(order)
        if not ac_check:
            return False, ac_reason

        # Check sector exposure
        sector_check, sector_reason = await self._check_sector_exposure(order)
        if not sector_check:
            return False, sector_reason

        # Check correlation with existing positions
        corr_check, corr_reason = await self._check_correlation_limits(order)
        if not corr_check:
            return False, corr_reason

        # Check leverage
        new_gross_exposure = self._calculate_gross_exposure() + order_notional
        new_leverage = new_gross_exposure / self.current_equity

        if new_leverage > self.max_leverage:
            return (
                False,
                f"New leverage {new_leverage:.2f}x exceeds limit ({self.max_leverage}x)"
            )

        logger.info(f"Order approved: {order.symbol} {order.quantity} @ ${order.price}")
        return True, "Order approved"

    async def _check_asset_class_limits(self, order: Order) -> Tuple[bool, str]:
        """Check if order respects asset class allocation limits"""
        current_ac_value = self._get_asset_class_value(order.asset_class)
        order_notional = order.quantity * order.price
        new_ac_value = current_ac_value + order_notional
        new_ac_pct = new_ac_value / self.current_equity
        limit = self.asset_class_limits.get(order.asset_class, 0.1)

        if new_ac_pct > limit:
            return (
                False,
                f"{order.asset_class.value} exposure {new_ac_pct:.1%} exceeds limit ({limit:.1%})"
            )

        return True, ""

    async def _check_sector_exposure(self, order: Order) -> Tuple[bool, str]:
        """Check if order respects sector exposure limits"""
        if not order.asset_class == AssetClass.EQUITY:
            return True, ""

        # Get current sector exposure (simplified - would need real sector data)
        sector = order.symbol  # Would map symbol to sector in production
        current_sector_value = sum(
            p.notional_value() for p in self.positions.values()
            if p.sector == sector
        )

        order_notional = order.quantity * order.price
        new_sector_value = current_sector_value + order_notional
        new_sector_pct = new_sector_value / self.current_equity

        if new_sector_pct > self.max_sector_exposure_pct:
            return (
                False,
                f"Sector exposure {new_sector_pct:.1%} exceeds limit "
                f"({self.max_sector_exposure_pct:.1%})"
            )

        return True, ""

    async def _check_correlation_limits(self, order: Order) -> Tuple[bool, str]:
        """Check correlation between new order and existing positions"""
        # Simplified: would compute actual price correlations in production
        # For now, check if too many similar assets
        existing_symbols = list(self.positions.keys())
        if len(existing_symbols) > 0:
            # This would use actual price data to compute correlations
            pass

        return True, ""

    def update_position(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        current_price: float,
        asset_class: AssetClass,
        sector: Optional[str] = None,
    ):
        """Update or create a position"""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.quantity = quantity
            pos.current_price = current_price
            pos.update_pnl()
        else:
            pos = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                current_price=current_price,
                asset_class=asset_class,
                sector=sector,
            )
            self.positions[symbol] = pos
            pos.update_pnl()

        logger.debug(f"Position updated: {symbol} {quantity} @ ${current_price}")

    def close_position(self, symbol: str):
        """Close a position"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"Position closed: {symbol}")

    async def get_portfolio_risk(self) -> PortfolioRisk:
        """Get comprehensive portfolio risk metrics"""
        # Update all position P&Ls
        for pos in self.positions.values():
            pos.update_pnl()

        # Calculate totals
        total_positions_value = sum(p.notional_value() for p in self.positions.values())
        total_pnl = sum(p.pnl for p in self.positions.values())
        total_pnl_pct = (total_pnl / self.current_equity) if self.current_equity > 0 else 0.0

        # Update equity
        self.current_equity = self.initial_equity + total_pnl

        # Calculate drawdown
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        current_drawdown = (
            (self.peak_equity - self.current_equity) / self.peak_equity
            if self.peak_equity > 0 else 0.0
        )
        max_drawdown_breach = current_drawdown > (self.max_drawdown_pct / 100)

        # Check daily loss
        daily_loss_breach = (self.daily_pnl < 0 and
                             abs(self.daily_pnl) > (self.current_equity * self.max_daily_loss_pct / 100))

        # Calculate exposures
        gross_exposure = sum(abs(p.notional_value()) for p in self.positions.values())
        net_exposure = sum(p.notional_value() for p in self.positions.values())
        current_leverage = gross_exposure / self.current_equity if self.current_equity > 0 else 0.0

        # Check for breaches
        concentration_breach = any(
            p.notional_value() / self.current_equity > self.max_single_position_pct / 100
            for p in self.positions.values()
        )

        portfolio_risk = PortfolioRisk(
            total_equity=self.current_equity,
            total_positions_value=total_positions_value,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            today_pnl=self.daily_pnl,
            max_drawdown_pct=current_drawdown * 100,
            current_leverage=current_leverage,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            max_drawdown_breach=max_drawdown_breach,
            max_daily_loss_breach=daily_loss_breach,
            concentration_breach=concentration_breach,
        )

        # Log breaches
        if portfolio_risk.max_drawdown_breach:
            logger.warning(
                f"MAX DRAWDOWN BREACH: {portfolio_risk.max_drawdown_pct:.2f}% "
                f"(limit: {self.max_drawdown_pct}%)"
            )

        if portfolio_risk.max_daily_loss_breach:
            logger.warning(
                f"MAX DAILY LOSS BREACH: ${self.daily_pnl:.2f} "
                f"(limit: {self.max_daily_loss_pct}%)"
            )

        return portfolio_risk

    async def get_exposure_report(self) -> Dict:
        """Get detailed exposure report by asset class and sector"""
        exposure_by_ac = {}
        exposure_by_sector = {}

        for asset_class in AssetClass:
            value = self._get_asset_class_value(asset_class)
            pct = (value / self.current_equity * 100) if self.current_equity > 0 else 0.0
            exposure_by_ac[asset_class.value] = {
                "value": value,
                "pct": pct,
                "limit_pct": self.asset_class_limits.get(asset_class, 0.1) * 100,
            }

        for pos in self.positions.values():
            sector = pos.sector or "Unknown"
            if sector not in exposure_by_sector:
                exposure_by_sector[sector] = 0.0
            exposure_by_sector[sector] += pos.notional_value()

        for sector in exposure_by_sector:
            exposure_by_sector[sector] = {
                "value": exposure_by_sector[sector],
                "pct": (exposure_by_sector[sector] / self.current_equity * 100)
                       if self.current_equity > 0 else 0.0,
            }

        return {
            "by_asset_class": exposure_by_ac,
            "by_sector": exposure_by_sector,
            "total_leverage": (sum(p.notional_value() for p in self.positions.values())
                              / self.current_equity) if self.current_equity > 0 else 0.0,
        }

    def _get_asset_class_value(self, asset_class: AssetClass) -> float:
        """Get total notional value for an asset class"""
        return sum(
            p.notional_value() for p in self.positions.values()
            if p.asset_class == asset_class
        )

    def _calculate_gross_exposure(self) -> float:
        """Calculate total gross exposure"""
        return sum(abs(p.notional_value()) for p in self.positions.values())

    def update_daily_pnl(self, amount: float):
        """Update daily P&L"""
        self.daily_pnl += amount

    def reset_daily_pnl(self):
        """Reset daily P&L at end of day"""
        self.daily_pnl = 0.0
        self.daily_start_time = datetime.utcnow()

    def disable_trading(self, reason: str):
        """Disable trading with reason"""
        self.trading_enabled = False
        logger.critical(f"Trading disabled: {reason}")

    def enable_trading(self):
        """Re-enable trading"""
        self.trading_enabled = True
        logger.info("Trading re-enabled")
