"""
Strategy management endpoints.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_engine
from core.engine import TradingEngine
from core.models import StrategyPerformance as Strategy

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class StrategyMetrics(BaseModel):
    total_trades: int
    win_rate: float
    avg_pnl: float
    best_trade: float
    worst_trade: float
    profit_factor: float
    sharpe_ratio: float


class StrategyResponse(BaseModel):
    name: str
    status: str
    enabled: bool
    description: Optional[str]
    entry_condition: Optional[str]
    exit_condition: Optional[str]
    risk_per_trade: float
    position_size: float
    max_positions: int
    created_at: datetime
    updated_at: datetime
    metrics: StrategyMetrics

    class Config:
        from_attributes = True


class StrategyListResponse(BaseModel):
    strategies: list[StrategyResponse]
    total: int
    active: int


class SignalResponse(BaseModel):
    id: str
    strategy: str
    symbol: str
    signal_type: str
    strength: float
    timestamp: datetime
    data: dict[str, Any]


class SignalListResponse(BaseModel):
    signals: list[SignalResponse]
    total: int


class BacktestRequest(BaseModel):
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(100000.0, gt=0)
    params: Optional[dict[str, Any]] = None


class BacktestMetrics(BaseModel):
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_duration: float


class BacktestResponse(BaseModel):
    strategy: str
    status: str
    metrics: BacktestMetrics
    start_date: datetime
    end_date: datetime
    timestamp: datetime


class StrategyParamsRequest(BaseModel):
    params: dict[str, Any]
    comment: Optional[str] = None


@router.get("/strategies")
async def list_strategies_endpoint(
    status_filter: Optional[str] = Query(None, alias="status"),
    engine: TradingEngine = Depends(get_engine),
):
    """
    List all strategies with status and performance.
    """
    try:
        strategies_dict = getattr(engine, 'strategies', {})
        strategy_list = []
        for name, strat in strategies_dict.items():
            strategy_list.append({
                "name": name,
                "status": getattr(strat, 'status', 'active'),
                "enabled": getattr(strat, 'enabled', True),
                "description": getattr(strat, 'description', None),
                "entry_condition": getattr(strat, 'entry_condition', None),
                "exit_condition": getattr(strat, 'exit_condition', None),
                "risk_per_trade": getattr(strat, 'risk_per_trade', 0.02),
                "position_size": getattr(strat, 'position_size', 0.1),
                "max_positions": getattr(strat, 'max_positions', 5),
                "created_at": getattr(strat, 'created_at', datetime.utcnow()).isoformat() if hasattr(getattr(strat, 'created_at', None), 'isoformat') else datetime.utcnow().isoformat(),
                "updated_at": getattr(strat, 'updated_at', datetime.utcnow()).isoformat() if hasattr(getattr(strat, 'updated_at', None), 'isoformat') else datetime.utcnow().isoformat(),
                "metrics": {
                    "total_trades": getattr(strat, 'total_trades', 0),
                    "win_rate": getattr(strat, 'win_rate', 0.0),
                    "avg_pnl": getattr(strat, 'avg_pnl', 0.0),
                    "best_trade": getattr(strat, 'best_trade', 0.0),
                    "worst_trade": getattr(strat, 'worst_trade', 0.0),
                    "profit_factor": getattr(strat, 'profit_factor', 0.0),
                    "sharpe_ratio": getattr(strat, 'sharpe_ratio', 0.0),
                },
            })

        if status_filter:
            strategy_list = [s for s in strategy_list if s["status"] == status_filter]

        active_count = sum(1 for s in strategy_list if s.get("enabled", False))

        return {
            "strategies": strategy_list,
            "total": len(strategy_list),
            "active": active_count,
        }

    except Exception as e:
        logger.error(f"Error listing strategies: {e}", exc_info=True)
        return {"strategies": [], "total": 0, "active": 0}


@router.get("/strategies/list")
async def list_strategies_alias(
    engine: TradingEngine = Depends(get_engine),
):
    """List all strategies (alias)."""
    try:
        return await list_strategies_endpoint(engine=engine)
    except Exception:
        return []


@router.get("/strategies/{name}", response_model=StrategyResponse)
async def get_strategy(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed strategy information."""
    try:
        stmt = select(Strategy).where(Strategy.name == name)
        strategy = (await db.execute(stmt)).scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        return StrategyResponse.model_validate(strategy)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch strategy",
        )


@router.post("/strategies/{name}/enable", status_code=status.HTTP_200_OK)
async def enable_strategy(
    name: str,
    engine: TradingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
):
    """Enable a strategy."""
    try:
        stmt = select(Strategy).where(Strategy.name == name)
        strategy = (await db.execute(stmt)).scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        strategy.enabled = True
        strategy.status = "active"
        db.add(strategy)
        await db.commit()

        await engine.enable_strategy(name)

        return {"message": f"Strategy {name} enabled", "timestamp": datetime.utcnow()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling strategy: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable strategy",
        )


@router.post("/strategies/{name}/disable", status_code=status.HTTP_200_OK)
async def disable_strategy(
    name: str,
    engine: TradingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
):
    """Disable a strategy."""
    try:
        stmt = select(Strategy).where(Strategy.name == name)
        strategy = (await db.execute(stmt)).scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        strategy.enabled = False
        strategy.status = "inactive"
        db.add(strategy)
        await db.commit()

        await engine.disable_strategy(name)

        return {"message": f"Strategy {name} disabled", "timestamp": datetime.utcnow()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling strategy: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable strategy",
        )


@router.put("/strategies/{name}/params", status_code=status.HTTP_200_OK)
async def update_strategy_params(
    name: str,
    params_request: StrategyParamsRequest,
    engine: TradingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
):
    """Update strategy parameters."""
    try:
        stmt = select(Strategy).where(Strategy.name == name)
        strategy = (await db.execute(stmt)).scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        await engine.update_strategy_params(name, params_request.params)

        return {
            "message": f"Strategy {name} parameters updated",
            "timestamp": datetime.utcnow(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating strategy params: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update strategy parameters",
        )


@router.get("/strategies/{name}/signals", response_model=SignalListResponse)
async def get_strategy_signals(
    name: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get recent signals from strategy."""
    try:
        from core.models import Signal

        stmt = select(Signal).where(Signal.strategy == name).order_by(Signal.timestamp.desc()).limit(limit)

        signals = (await db.execute(stmt)).scalars().all()

        return SignalListResponse(
            signals=[
                SignalResponse(
                    id=s.id,
                    strategy=s.strategy,
                    symbol=s.symbol,
                    signal_type=s.signal_type,
                    strength=s.strength,
                    timestamp=s.timestamp,
                    data=s.data or {},
                )
                for s in signals
            ],
            total=len(signals),
        )

    except Exception as e:
        logger.error(f"Error fetching signals: {e}", exc_info=True)
        return SignalListResponse(signals=[], total=0)


@router.post("/strategies/{name}/backtest", response_model=BacktestResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_strategy_backtest(
    name: str,
    backtest_request: BacktestRequest,
    engine: TradingEngine = Depends(get_engine),
):
    """Run backtest with specified parameters."""
    try:
        stmt = select(Strategy).where(Strategy.name == name)
        strategy = (await db.execute(stmt)).scalar_one_or_none()

        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        # TODO: Implement backtest execution
        # This would spawn a background task to run the backtest
        result = await engine.run_backtest(
            strategy_name=name,
            start_date=backtest_request.start_date,
            end_date=backtest_request.end_date,
            initial_capital=backtest_request.initial_capital,
            params=backtest_request.params,
        )

        return BacktestResponse(
            strategy=name,
            status="in_progress",
            metrics=BacktestMetrics(
                total_return=0.0,
                annual_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
                avg_trade_duration=0.0,
            ),
            start_date=backtest_request.start_date,
            end_date=backtest_request.end_date,
            timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running backtest: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run backtest",
        )
