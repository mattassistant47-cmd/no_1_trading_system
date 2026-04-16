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


@router.get("/positions")
async def get_positions(engine: TradingEngine = Depends(get_engine)):
    """Get all open positions from Alpaca (live data)."""
    try:
        broker = engine.brokers.get("alpaca")
        if not broker or not broker._connected:
            return {"positions": [], "total": 0, "total_unrealized_pnl": 0.0, "total_realized_pnl": 0.0}

        alpaca_positions = await broker.get_positions()
        portfolio_value = engine.portfolio_value or 100000.0

        positions_list = []
        total_unrealized = 0.0
        for p in alpaca_positions:
            qty = float(p.quantity)
            entry = float(p.avg_entry_price)
            current = float(p.current_price) if p.current_price else entry
            unreal = float(p.unrealized_pl) if p.unrealized_pl else 0.0
            market_val = float(p.market_value) if p.market_value else qty * current
            pct_change = ((current - entry) / entry * 100) if entry else 0.0
            portfolio_pct = (abs(market_val) / portfolio_value * 100) if portfolio_value else 0.0
            side = "long" if qty > 0 else "short"

            positions_list.append({
                "id": p.symbol,  # use symbol as id
                "symbol": p.symbol,
                "qty": qty,
                "side": side,
                "entryPrice": entry,
                "currentPrice": current,
                "marketValue": market_val,
                "unrealizedPnL": unreal,
                "percentChange": pct_change,
                "portfolioPercent": portfolio_pct,
                "strategy": getattr(p, 'strategy', 'manual'),
                "assetClass": getattr(p, 'asset_class', 'equity'),
            })
            total_unrealized += unreal

        return {
            "positions": positions_list,
            "total": len(positions_list),
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": 0.0,
        }
    except Exception as e:
        logger.error(f"Error fetching positions: {e}", exc_info=True)
        return {"positions": [], "total": 0, "total_unrealized_pnl": 0.0, "total_realized_pnl": 0.0}


@router.get("/positions/open")
async def get_open_positions(engine: TradingEngine = Depends(get_engine)):
    """Get open positions (alias for /positions)."""
    return await get_positions(engine=engine)


@router.get("/positions/exposure")
async def get_exposure(engine: TradingEngine = Depends(get_engine)):
    """Get real exposure breakdown from Alpaca positions."""
    try:
        broker = engine.brokers.get("alpaca")
        portfolio_value = engine.portfolio_value or 100000.0

        if not broker or not broker._connected:
            return {
                "total_exposure": 0.0, "long_exposure": 0.0, "short_exposure": 0.0,
                "net_exposure": 0.0, "by_asset_class": {}, "by_sector": {}, "by_strategy": {},
                "by_symbol": []
            }

        positions = await broker.get_positions()
        long_val = sum(float(p.market_value or 0) for p in positions if float(p.quantity or 0) > 0)
        short_val = sum(abs(float(p.market_value or 0)) for p in positions if float(p.quantity or 0) < 0)

        # Convert to percentages
        long_pct = (long_val / portfolio_value * 100) if portfolio_value else 0.0
        short_pct = (short_val / portfolio_value * 100) if portfolio_value else 0.0
        total_pct = long_pct + short_pct
        net_pct = long_pct - short_pct

        by_asset_class = {}
        by_symbol = []
        for p in positions:
            ac = getattr(p, 'asset_class', 'equity')
            val = float(p.market_value or 0)
            by_asset_class[ac] = by_asset_class.get(ac, 0) + val
            by_symbol.append({
                "symbol": p.symbol,
                "value": val,
                "percent": (abs(val) / portfolio_value * 100) if portfolio_value else 0,
            })

        return {
            "total_exposure": total_pct,
            "long_exposure": long_pct,
            "short_exposure": short_pct,
            "net_exposure": net_pct,
            "by_asset_class": by_asset_class,
            "by_sector": {},
            "by_strategy": {},
            "by_symbol": by_symbol,
        }
    except Exception as e:
        logger.error(f"Error computing exposure: {e}", exc_info=True)
        return {
            "total_exposure": 0.0, "long_exposure": 0.0, "short_exposure": 0.0,
            "net_exposure": 0.0, "by_asset_class": {}, "by_sector": {}, "by_strategy": {},
            "by_symbol": []
        }


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
