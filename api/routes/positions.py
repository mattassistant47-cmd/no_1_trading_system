"""
Position management endpoints.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_engine
from core.engine import TradingEngine
from core.models import Position

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class PositionResponse(BaseModel):
    id: str
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    entry_time: datetime
    unrealized_pnl: float
    unrealized_pnl_percentage: float
    realized_pnl: float
    side: str
    strategy: str
    broker: str
    status: str

    class Config:
        from_attributes = True


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]
    total: int
    total_unrealized_pnl: float
    total_realized_pnl: float


class HistoricalPosition(BaseModel):
    id: str
    symbol: str
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    realized_pnl: float
    realized_pnl_percentage: float
    duration_hours: float
    strategy: str


class HistoricalPositionListResponse(BaseModel):
    positions: list[HistoricalPosition]
    total: int


class ExposureResponse(BaseModel):
    by_sector: dict[str, float]
    by_asset_class: dict[str, float]
    by_strategy: dict[str, float]
    total_exposure: float
    long_exposure: float
    short_exposure: float
    net_exposure: float


class ClosePositionRequest(BaseModel):
    price: Optional[float] = Field(None, description="Close at specific price, None for market")
    comment: Optional[str] = None


class ClosePositionResponse(BaseModel):
    position_id: str
    symbol: str
    closed_quantity: float
    close_price: float
    realized_pnl: float
    status: str
    timestamp: datetime


@router.get("/positions", response_model=PositionListResponse)
async def list_open_positions(
    symbol: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all open positions with unrealized P&L.
    """
    try:
        query = select(Position).where(Position.status == "open")

        filters = []
        if symbol:
            filters.append(Position.symbol == symbol)
        if strategy:
            filters.append(Position.strategy == strategy)

        if filters:
            query = query.where(and_(*filters))

        positions = (await db.execute(query)).scalars().all()

        total_unrealized = sum(p.unrealized_pnl for p in positions if p.unrealized_pnl)
        total_realized = sum(p.realized_pnl for p in positions if p.realized_pnl)

        return PositionListResponse(
            positions=[PositionResponse.model_validate(p) for p in positions],
            total=len(positions),
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
        )

    except Exception as e:
        logger.error(f"Error listing positions: {e}", exc_info=True)
        return PositionListResponse(
            positions=[], total=0,
            total_unrealized_pnl=0.0, total_realized_pnl=0.0,
        )


@router.get("/positions/open")
async def get_open_positions(
    db: AsyncSession = Depends(get_db),
    engine: TradingEngine = Depends(get_engine),
):
    """Get open positions (alias for /positions)."""
    try:
        return await list_open_positions(db=db)
    except Exception:
        return []


@router.get("/positions/history", response_model=HistoricalPositionListResponse)
async def get_position_history(
    symbol: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical positions (closed positions).
    """
    try:
        query = select(Position).where(Position.status == "closed")

        filters = []
        if symbol:
            filters.append(Position.symbol == symbol)
        if strategy:
            filters.append(Position.strategy == strategy)

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(Position.exit_time.desc()).limit(limit)

        positions = (await db.execute(query)).scalars().all()

        history = []
        for p in positions:
            if p.exit_time and p.exit_price:
                duration = (p.exit_time - p.entry_time).total_seconds() / 3600
                history.append(
                    HistoricalPosition(
                        id=p.id,
                        symbol=p.symbol,
                        quantity=p.quantity,
                        entry_price=p.entry_price,
                        exit_price=p.exit_price,
                        entry_time=p.entry_time,
                        exit_time=p.exit_time,
                        realized_pnl=p.realized_pnl or 0,
                        realized_pnl_percentage=(p.realized_pnl / (p.entry_price * p.quantity) * 100) if p.realized_pnl else 0,
                        duration_hours=duration,
                        strategy=p.strategy,
                    )
                )

        return HistoricalPositionListResponse(
            positions=history,
            total=len(history),
        )

    except Exception as e:
        logger.error(f"Error fetching position history: {e}", exc_info=True)
        return HistoricalPositionListResponse(positions=[], total=0)


@router.post("/positions/{position_id}/close", response_model=ClosePositionResponse)
async def close_position(
    position_id: str,
    close_request: ClosePositionRequest,
    engine: TradingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually close a position.
    """
    try:
        stmt = select(Position).where(Position.id == position_id)
        position = (await db.execute(stmt)).scalar_one_or_none()

        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Position not found",
            )

        if position.status != "open":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Position is not open",
            )

        # Close position via engine
        close_price = close_request.price or position.current_price
        realized_pnl = await engine.close_position(
            position_id=position_id,
            price=close_price,
            comment=close_request.comment,
        )

        return ClosePositionResponse(
            position_id=position_id,
            symbol=position.symbol,
            closed_quantity=position.quantity,
            close_price=close_price,
            realized_pnl=realized_pnl,
            status="closed",
            timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing position: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close position",
        )


@router.get("/positions/exposure", response_model=ExposureResponse)
async def get_exposure(
    engine: TradingEngine = Depends(get_engine),
):
    """
    Get exposure breakdown by sector, asset class, and strategy.
    """
    try:
        # TODO: Implement exposure calculation
        # Placeholder implementation
        return ExposureResponse(
            by_sector={},
            by_asset_class={},
            by_strategy={},
            total_exposure=engine.portfolio_value,
            long_exposure=0,
            short_exposure=0,
            net_exposure=0,
        )

    except Exception as e:
        logger.error(f"Error fetching exposure: {e}", exc_info=True)
        return ExposureResponse(
            by_sector={}, by_asset_class={}, by_strategy={},
            total_exposure=0.0, long_exposure=0.0,
            short_exposure=0.0, net_exposure=0.0,
        )
