"""
Dashboard endpoints for portfolio overview and metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_engine
from config.settings import settings
from core.engine import TradingEngine
from core.models import Trade

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    cumulative_pnl: float


class EquityCurveResponse(BaseModel):
    data: list[EquityPoint]
    start_date: datetime
    end_date: datetime


class AllocationItem(BaseModel):
    symbol: str
    asset_class: str
    value: float
    percentage: float
    unrealized_pnl: float


class AllocationResponse(BaseModel):
    total_value: float
    by_asset_class: dict[str, float]
    by_symbol: list[AllocationItem]


class PerformanceMetrics(BaseModel):
    total_return: float = Field(..., description="Total return percentage")
    annual_return: float = Field(..., description="Annualized return percentage")
    sharpe_ratio: float = Field(..., description="Sharpe ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    win_rate: float = Field(..., description="Win rate percentage")
    profit_factor: float = Field(..., description="Profit factor")
    avg_trade_duration_hours: float = Field(..., description="Average trade duration")


class DashboardSummary(BaseModel):
    portfolio_value: float
    cash: float
    invested: float
    daily_pnl: float
    daily_pnl_percentage: float
    total_pnl: float
    total_pnl_percentage: float
    win_rate: float
    sharpe_ratio: float
    total_trades: int
    open_positions: int
    timestamp: datetime


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    engine: TradingEngine = Depends(get_engine),
):
    """
    Get portfolio summary: value, P&L, metrics.
    """
    try:
        # Get portfolio data from engine
        initial_capital = settings.trading.initial_capital
        portfolio_value = getattr(engine, 'portfolio_value', initial_capital)
        cash = getattr(engine, 'cash', initial_capital)
        invested = portfolio_value - cash
        daily_pnl = getattr(engine, 'daily_pnl', 0.0)
        daily_pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0
        total_pnl = getattr(engine, 'total_pnl', 0.0)
        initial_capital = getattr(engine, 'initial_capital', initial_capital)
        total_pnl_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0

        # Get trade statistics
        stmt = select(func.count(Trade.id))
        result = await db.execute(stmt)
        total_trades = result.scalar() or 0

        # Calculate metrics
        win_rate = getattr(engine, 'win_rate', 0.0)
        sharpe_ratio = getattr(engine, 'sharpe_ratio', 0.0)
        open_positions = len(getattr(engine, 'open_positions', []))

        return DashboardSummary(
            portfolio_value=portfolio_value,
            cash=cash,
            invested=invested,
            daily_pnl=daily_pnl,
            daily_pnl_percentage=daily_pnl_pct,
            total_pnl=total_pnl,
            total_pnl_percentage=total_pnl_pct,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            total_trades=total_trades,
            open_positions=open_positions,
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard summary: {e}", exc_info=True)
        initial_capital = settings.trading.initial_capital
        return DashboardSummary(
            portfolio_value=initial_capital, cash=initial_capital, invested=0.0,
            daily_pnl=0.0, daily_pnl_percentage=0.0,
            total_pnl=0.0, total_pnl_percentage=0.0,
            win_rate=0.0, sharpe_ratio=0.0,
            total_trades=0, open_positions=0,
            timestamp=datetime.utcnow(),
        )


@router.get("/dashboard/equity-curve", response_model=EquityCurveResponse)
async def get_equity_curve(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical equity curve data.
    Returns time series of portfolio value.
    """
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # TODO: Query equity curve from database
        # This is placeholder logic
        data = []
        current_date = start_date
        initial_capital = settings.trading.initial_capital
        current_equity = initial_capital

        while current_date <= end_date:
            import random

            daily_return = random.uniform(-0.02, 0.02)
            current_equity *= (1 + daily_return)

            data.append(
                EquityPoint(
                    timestamp=current_date,
                    equity=current_equity,
                    cumulative_pnl=current_equity - initial_capital,
                )
            )

            current_date += timedelta(hours=1)

        return EquityCurveResponse(
            data=data,
            start_date=start_date,
            end_date=end_date,
        )

    except Exception as e:
        logger.error(f"Error fetching equity curve: {e}", exc_info=True)
        return EquityCurveResponse(
            data=[], start_date=datetime.utcnow(), end_date=datetime.utcnow(),
        )


@router.get("/dashboard/allocation", response_model=AllocationResponse)
async def get_asset_allocation(
    engine: TradingEngine = Depends(get_engine),
):
    """
    Get current asset allocation breakdown.
    """
    try:
        portfolio_value = getattr(engine, 'portfolio_value', settings.trading.initial_capital)
        allocation_by_asset = {}
        allocation_by_symbol = []

        # TODO: Get positions from engine
        # Placeholder implementation
        total_value = 0

        return AllocationResponse(
            total_value=portfolio_value,
            by_asset_class=allocation_by_asset,
            by_symbol=allocation_by_symbol,
        )

    except Exception as e:
        logger.error(f"Error fetching allocation: {e}", exc_info=True)
        return AllocationResponse(
            total_value=0.0, by_asset_class={}, by_symbol=[],
        )


@router.get("/dashboard/metrics", response_model=PerformanceMetrics)
async def get_performance_metrics(
    engine: TradingEngine = Depends(get_engine),
):
    """
    Get key performance metrics.
    """
    try:
        return PerformanceMetrics(
            total_return=getattr(engine, 'total_pnl_percentage', 0.0),
            annual_return=getattr(engine, 'annual_return', 0.0),
            sharpe_ratio=getattr(engine, 'sharpe_ratio', 0.0),
            max_drawdown=getattr(engine, 'max_drawdown', 0.0),
            win_rate=getattr(engine, 'win_rate', 0.0),
            profit_factor=getattr(engine, 'profit_factor', 0.0),
            avg_trade_duration_hours=getattr(engine, 'avg_trade_duration_hours', 0.0),
        )

    except Exception as e:
        logger.error(f"Error fetching metrics: {e}", exc_info=True)
        return PerformanceMetrics(
            total_return=0.0, annual_return=0.0, sharpe_ratio=0.0,
            max_drawdown=0.0, win_rate=0.0, profit_factor=0.0,
            avg_trade_duration_hours=0.0,
        )


@router.get("/dashboard/overview")
async def get_dashboard_overview(
    db: AsyncSession = Depends(get_db),
    engine: TradingEngine = Depends(get_engine),
):
    """Aggregated dashboard overview with real Alpaca data."""
    try:
        # Portfolio data from Alpaca account
        broker = engine.brokers.get("alpaca")
        portfolio_value = engine.portfolio_value or settings.trading.initial_capital
        cash = engine.cash or portfolio_value
        daily_pnl = 0.0

        if broker and broker._connected:
            try:
                account = await broker.get_account()
                # Account dataclass: balance=portfolio_value, equity, cash
                portfolio_value = float(account.balance or portfolio_value)
                cash = float(account.cash or cash)
                # Try to get last_equity from raw Alpaca client for daily PnL
                try:
                    raw_account = broker.client.get_account()
                    last_equity = float(raw_account.last_equity or 0)
                    current_equity = float(raw_account.equity or portfolio_value)
                    daily_pnl = current_equity - last_equity if last_equity else 0.0
                except Exception:
                    daily_pnl = 0.0
            except Exception as e:
                logger.debug(f"Could not get Alpaca account: {e}")

        invested = portfolio_value - cash
        initial_capital = engine.initial_capital or settings.trading.initial_capital
        total_pnl = portfolio_value - initial_capital
        total_pnl_pct = (total_pnl / initial_capital * 100) if initial_capital else 0.0
        daily_pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value else 0.0

        # Equity curve from PortfolioSnapshot table
        equity_curve = []
        try:
            from core.models import PortfolioSnapshot
            stmt = select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.desc()).limit(30)
            result = await db.execute(stmt)
            snapshots = list(reversed(list(result.scalars().all())))
            for s in snapshots:
                equity_curve.append({
                    "date": s.timestamp.strftime("%Y-%m-%d %H:%M") if s.timestamp else "",
                    "value": float(s.total_value or 0),
                    "cumulativePnl": float(s.total_profit_loss or 0),
                })
        except Exception as e:
            logger.debug(f"Could not fetch equity curve: {e}")

        # If no snapshots yet, seed with current value
        if not equity_curve:
            equity_curve = [{
                "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                "value": portfolio_value,
                "cumulativePnl": total_pnl,
            }]

        # Asset allocation
        asset_allocation = [{"name": "Cash", "value": cash}]
        if broker and broker._connected and invested > 0:
            try:
                positions = await broker.get_positions()
                by_class = {}
                for p in positions:
                    ac = getattr(p, 'asset_class', 'Equity') or 'Equity'
                    ac = ac.capitalize() if isinstance(ac, str) else 'Equity'
                    val = abs(float(p.market_value or 0))
                    by_class[ac] = by_class.get(ac, 0) + val
                for name, val in by_class.items():
                    asset_allocation.append({"name": name, "value": val})
            except Exception:
                asset_allocation.append({"name": "Equity", "value": invested})

        # Strategy performance
        strategy_performance = []
        for name, strat in (engine.strategies or {}).items():
            try:
                metrics = getattr(strat, 'metrics', None)
                strategy_performance.append({
                    "name": name,
                    "return": float(getattr(metrics, 'avg_pnl', 0) or 0),
                    "sharpe": float(getattr(metrics, 'sharpe_ratio', 0) or 0),
                    "trades": int(getattr(metrics, 'total_trades', 0) or 0),
                })
            except Exception:
                strategy_performance.append({"name": name, "return": 0.0, "sharpe": 0.0, "trades": 0})

        open_positions = 0
        if broker and broker._connected:
            try:
                positions = await broker.get_positions()
                open_positions = len(positions)
            except Exception:
                open_positions = len(getattr(engine, 'open_positions', []))

        return {
            "portfolioValue": portfolio_value,
            "cash": cash,
            "invested": invested,
            "dailyPnl": daily_pnl,
            "dailyPnlPercentage": daily_pnl_pct,
            "totalPnl": total_pnl,
            "totalPnlPercentage": total_pnl_pct,
            "winRate": float(getattr(engine, 'win_rate', 0) or 0),
            "sharpeRatio": float(getattr(engine, 'sharpe_ratio', 0) or 0),
            "totalTrades": 0,
            "openPositions": open_positions,
            "equityCurve": equity_curve,
            "assetAllocation": asset_allocation,
            "strategyPerformance": strategy_performance,
            "recentTrades": [],
            "activeSignals": [],
            "activeStrategies": len(engine.strategies or {}),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Dashboard overview error: {e}", exc_info=True)
        initial_capital = settings.trading.initial_capital
        return {
            "portfolioValue": initial_capital, "cash": initial_capital, "invested": 0.0,
            "dailyPnl": 0.0, "dailyPnlPercentage": 0.0,
            "totalPnl": 0.0, "totalPnlPercentage": 0.0,
            "winRate": 0.0, "sharpeRatio": 0.0,
            "totalTrades": 0, "openPositions": 0,
            "equityCurve": [], "assetAllocation": [], "strategyPerformance": [],
            "recentTrades": [], "activeSignals": [], "activeStrategies": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }
