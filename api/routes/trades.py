"""
Trade management endpoints.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_engine
from core.engine import TradingEngine
from core.models import Trade

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class TradeResponse(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_time: datetime
    exit_price: Optional[float]
    exit_time: Optional[datetime]
    status: str
    pnl: Optional[float]
    pnl_percentage: Optional[float]
    strategy: str
    broker: str

    class Config:
        from_attributes = True


class TradeListResponse(BaseModel):
    trades: list[TradeResponse]
    total: int
    page: int
    page_size: int


class TradeStatsResponse(BaseModel):
    total_trades: int
    closed_trades: int
    open_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_pnl: float
    best_trade: float
    worst_trade: float
    total_pnl: float
    profit_factor: float


class ManualTradeRequest(BaseModel):
    symbol: str
    side: str = Field(..., description="BUY or SELL")
    quantity: float = Field(..., gt=0)
    price: Optional[float] = Field(None, description="Limit price, None for market")
    strategy: str = "manual"
    comment: Optional[str] = None


class ManualTradeResponse(BaseModel):
    trade_id: str
    symbol: str
    side: str
    quantity: float
    price: Optional[float]
    status: str
    timestamp: datetime


@router.get("/trades")
async def list_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    strategy: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    engine: TradingEngine = Depends(get_engine),
):
    """
    List trades - pulls from Alpaca broker order history when DB is empty.
    """
    try:
        trades_list = []

        # Pull from Alpaca if connected
        broker = engine.brokers.get("alpaca") if engine and engine.brokers else None
        if broker and getattr(broker, "_connected", False) and hasattr(broker, "get_recent_filled_orders"):
            try:
                trades_list = await broker.get_recent_filled_orders(limit=50)
            except Exception as e:
                logger.debug(f"Failed to get Alpaca orders: {e}")

        # Apply filters
        if symbol:
            trades_list = [t for t in trades_list if t.get("symbol", "").upper() == symbol.upper()]
        if side:
            trades_list = [t for t in trades_list if t.get("side", "").lower() == side.lower()]
        if strategy:
            trades_list = [t for t in trades_list if t.get("strategy", "") == strategy]

        total = len(trades_list)

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        paginated = trades_list[start:end]

        return {
            "trades": paginated,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    except Exception as e:
        logger.error(f"Error listing trades: {e}", exc_info=True)
        return {"trades": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/trades/stats", response_model=TradeStatsResponse)
async def get_trade_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get trade statistics."""
    try:
        start_date = datetime.utcnow() - timedelta(days=days)

        # Query closed trades
        closed_query = select(Trade).where(
            and_(
                Trade.status == "closed",
                Trade.exit_time >= start_date,
            )
        )
        closed_trades = (await db.execute(closed_query)).scalars().all()

        # Query open trades
        open_query = select(Trade).where(Trade.status == "open")
        open_trades = (await db.execute(open_query)).scalars().all()

        total_trades = len(closed_trades) + len(open_trades)
        winning_trades = sum(1 for t in closed_trades if t.pnl and t.pnl > 0)
        losing_trades = sum(1 for t in closed_trades if t.pnl and t.pnl < 0)

        win_rate = (winning_trades / len(closed_trades) * 100) if closed_trades else 0
        avg_pnl = (sum(t.pnl for t in closed_trades if t.pnl) / len(closed_trades)) if closed_trades else 0
        best_trade = max((t.pnl for t in closed_trades if t.pnl), default=0)
        worst_trade = min((t.pnl for t in closed_trades if t.pnl), default=0)
        total_pnl = sum(t.pnl for t in closed_trades if t.pnl)

        # Profit factor: gross profit / gross loss
        gross_profit = sum(t.pnl for t in closed_trades if t.pnl and t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in closed_trades if t.pnl and t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

        return TradeStatsResponse(
            total_trades=total_trades,
            closed_trades=len(closed_trades),
            open_trades=len(open_trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            best_trade=best_trade,
            worst_trade=worst_trade,
            total_pnl=total_pnl,
            profit_factor=profit_factor,
        )

    except Exception as e:
        logger.error(f"Error fetching trade stats: {e}", exc_info=True)
        return TradeStatsResponse(
            total_trades=0, closed_trades=0, open_trades=0,
            winning_trades=0, losing_trades=0, win_rate=0.0,
            avg_pnl=0.0, best_trade=0.0, worst_trade=0.0,
            total_pnl=0.0, profit_factor=0.0,
        )


@router.get("/trades/history")
async def get_trades_history(
    engine: TradingEngine = Depends(get_engine),
):
    """Trade history (alias)."""
    try:
        return await list_trades(engine=engine)
    except Exception:
        return {"trades": [], "total": 0, "page": 1, "page_size": 20}


@router.get("/trades/pnl-distribution")
async def get_pnl_distribution():
    """P&L distribution chart data."""
    return {"buckets": [], "counts": []}


@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get single trade details."""
    try:
        stmt = select(Trade).where(Trade.id == trade_id)
        trade = (await db.execute(stmt)).scalar_one_or_none()

        if not trade:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trade not found",
            )

        return TradeResponse.model_validate(trade)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trade: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch trade",
        )


@router.post("/trades/manual", response_model=ManualTradeResponse, status_code=status.HTTP_201_CREATED)
async def submit_manual_trade(
    trade_request: ManualTradeRequest,
    engine: TradingEngine = Depends(get_engine),
):
    """
    Submit a manual trade override.
    Bypasses normal strategy logic.
    """
    try:
        # Validate side
        if trade_request.side.upper() not in ("BUY", "SELL"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Side must be BUY or SELL",
            )

        # Submit to engine
        trade_id = await engine.submit_manual_trade(
            symbol=trade_request.symbol,
            side=trade_request.side.upper(),
            quantity=trade_request.quantity,
            price=trade_request.price,
            strategy=trade_request.strategy,
            comment=trade_request.comment,
        )

        return ManualTradeResponse(
            trade_id=trade_id,
            symbol=trade_request.symbol,
            side=trade_request.side.upper(),
            quantity=trade_request.quantity,
            price=trade_request.price,
            status="pending",
            timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting manual trade: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit trade",
        )


# Import at end to avoid circular imports
from sqlalchemy import func
