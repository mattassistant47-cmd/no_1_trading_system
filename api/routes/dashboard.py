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
        portfolio_value = getattr(engine, 'portfolio_value', 100000.0)
        cash = getattr(engine, 'cash', 100000.0)
        invested = portfolio_value - cash
        daily_pnl = getattr(engine, 'daily_pnl', 0.0)
        daily_pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0
        total_pnl = getattr(engine, 'total_pnl', 0.0)
        initial_capital = getattr(engine, 'initial_capital', 100000.0)
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
        return DashboardSummary(
            portfolio_value=100000.0, cash=100000.0, invested=0.0,
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
        current_equity = 100000.0

        while current_date <= end_date:
            import random

            daily_return = random.uniform(-0.02, 0.02)
            current_equity *= (1 + daily_return)

            data.append(
                EquityPoint(
                    timestamp=current_date,
                    equity=current_equity,
                    cumulative_pnl=current_equity - 100000.0,
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
        portfolio_value = getattr(engine, 'portfolio_value', 100000.0)
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
    engine: TradingEngine = Depends(get_engine),
):
    """Aggregated dashboard overview for frontend."""
    try:
        return {
            "portfolioValue": getattr(engine, 'portfolio_value', 100000.0),
            "cash": getattr(engine, 'cash', 100000.0),
            "invested": getattr(engine, 'portfolio_value', 100000.0) - getattr(engine, 'cash', 100000.0),
            "dailyPnl": getattr(engine, 'daily_pnl', 0.0),
            "dailyPnlPercentage": 0.0,
            "totalPnl": getattr(engine, 'total_pnl', 0.0),
            "totalPnlPercentage": getattr(engine, 'total_pnl_percentage', 0.0),
            "winRate": getattr(engine, 'win_rate', 0.0),
            "sharpeRatio": getattr(engine, 'sharpe_ratio', 0.0),
            "totalTrades": 0,
            "openPositions": len(getattr(engine, 'open_positions', [])),
            "equityCurve": [],
            "recentTrades": [],
            "activeStrategies": len(getattr(engine, 'strategies', {})),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        return {
            "portfolioValue": 100000.0, "cash": 100000.0, "invested": 0.0,
            "dailyPnl": 0.0, "dailyPnlPercentage": 0.0,
            "totalPnl": 0.0, "totalPnlPercentage": 0.0,
            "winRate": 0.0, "sharpeRatio": 0.0,
            "totalTrades": 0, "openPositions": 0,
            "equityCurve": [], "recentTrades": [],
            "activeStrategies": 0, "timestamp": datetime.utcnow().isoformat(),
        }
