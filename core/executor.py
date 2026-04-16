"""
Order executor — tracks pending orders, polls for fills,
and updates positions/trades in the database on completion.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from brokers.base import BaseBroker, OrderStatus
from core.database import get_session
from core.events import EventBus, EventType, Event
from core.models import (
    Order as DBOrder,
    Trade as DBTrade,
    Position as DBPosition,
    OrderStatus as DBOrderStatus,
    PositionStatus,
    TradeType,
)


class OrderExecutor:
    """
    Tracks submitted orders, polls brokers for fill updates,
    and records fills in the database.
    """

    def __init__(
        self,
        brokers: Dict[str, any],
        event_bus: EventBus,
    ):
        self.brokers = brokers
        self.event_bus = event_bus
        self.pending_orders: List[Dict] = []

    async def track_order(
        self,
        order_id: str,
        broker_name: str,
        symbol: str = "",
        side: str = "",
        quantity: float = 0.0,
        price: float = 0.0,
        strategy_name: str = "",
    ) -> None:
        """Add an order to the tracking list."""
        self.pending_orders.append({
            "id": order_id,
            "broker": broker_name,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "strategy_name": strategy_name,
            "tracked_at": datetime.utcnow(),
        })
        logger.debug(f"Tracking order {order_id} on {broker_name} ({symbol})")

    async def check_fills(self) -> None:
        """Poll brokers for fill updates on all pending orders."""
        if not self.pending_orders:
            return

        filled = []
        for pending in self.pending_orders[:]:
            broker = self.brokers.get(pending["broker"])
            if not broker or not isinstance(broker, BaseBroker) or not broker.is_connected:
                continue

            try:
                status = await broker.get_order_status(pending["id"])

                if status.status == OrderStatus.FILLED:
                    await self._on_fill(pending, status)
                    filled.append(pending)
                elif status.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED):
                    logger.info(
                        f"Order {pending['id']} terminal status: {status.status.value}"
                    )
                    await self._on_terminal(pending, status)
                    filled.append(pending)

            except Exception as e:
                logger.error(f"Error checking order {pending['id']}: {e}")

        for item in filled:
            try:
                self.pending_orders.remove(item)
            except ValueError:
                pass

    async def _on_fill(self, order_info: Dict, fill_status) -> None:
        """Handle a filled order — update DB, create/close position, emit events."""
        symbol = order_info.get("symbol", fill_status.symbol)
        side = order_info.get("side", fill_status.side.value if fill_status.side else "buy")
        quantity = float(fill_status.filled_quantity or order_info.get("quantity", 0))
        fill_price = float(fill_status.avg_fill_price or order_info.get("price", 0))
        strategy_name = order_info.get("strategy_name", "unknown")
        broker_name = order_info.get("broker", "alpaca")

        logger.info(
            f"Order filled: {side} {quantity} {symbol} @ ${fill_price:.2f} "
            f"(strategy: {strategy_name})"
        )

        try:
            session = await get_session()
            async with session:
                # Update the order record
                from sqlalchemy import select, update
                stmt = (
                    update(DBOrder)
                    .where(DBOrder.broker_order_id == order_info["id"])
                    .values(
                        status=DBOrderStatus.FILLED,
                        filled_quantity=quantity,
                        filled_price=fill_price,
                        filled_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
                await session.execute(stmt)

                if side == "buy":
                    # Open or add to position
                    result = await session.execute(
                        select(DBPosition).where(
                            DBPosition.symbol == symbol,
                            DBPosition.status == PositionStatus.OPEN,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Average into existing position
                        old_cost = float(existing.quantity) * float(existing.average_entry_price)
                        new_cost = quantity * fill_price
                        total_qty = float(existing.quantity) + quantity
                        avg_price = (old_cost + new_cost) / total_qty if total_qty > 0 else fill_price
                        existing.quantity = total_qty
                        existing.average_entry_price = avg_price
                        existing.cost_basis = total_qty * avg_price
                        existing.current_price = fill_price
                        existing.market_value = total_qty * fill_price
                        existing.updated_at = datetime.utcnow()
                    else:
                        pos = DBPosition(
                            symbol=symbol,
                            quantity=quantity,
                            average_entry_price=fill_price,
                            current_price=fill_price,
                            cost_basis=quantity * fill_price,
                            market_value=quantity * fill_price,
                            unrealized_profit_loss=0,
                            unrealized_profit_loss_percent=0,
                            status=PositionStatus.OPEN,
                            strategy_name=strategy_name,
                            broker_name=broker_name,
                            opened_at=datetime.utcnow(),
                        )
                        session.add(pos)

                elif side == "sell":
                    # Close or reduce position
                    result = await session.execute(
                        select(DBPosition).where(
                            DBPosition.symbol == symbol,
                            DBPosition.status == PositionStatus.OPEN,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        entry_price = float(existing.average_entry_price)
                        pnl = (fill_price - entry_price) * quantity
                        pnl_pct = ((fill_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

                        remaining = float(existing.quantity) - quantity
                        if remaining <= 0.001:
                            # Fully closed
                            existing.status = PositionStatus.CLOSED
                            existing.closed_at = datetime.utcnow()
                            existing.quantity = 0
                        else:
                            existing.quantity = remaining
                            existing.market_value = remaining * fill_price
                        existing.current_price = fill_price
                        existing.updated_at = datetime.utcnow()

                        # Create trade record
                        trade = DBTrade(
                            symbol=symbol,
                            trade_type=TradeType.LONG,
                            entry_price=entry_price,
                            exit_price=fill_price,
                            quantity=quantity,
                            entry_quantity=quantity,
                            exit_quantity=quantity,
                            profit_loss=pnl,
                            profit_loss_percent=pnl_pct,
                            win=pnl > 0,
                            strategy_name=strategy_name,
                            broker_name=broker_name,
                            entry_time=existing.opened_at or datetime.utcnow(),
                            exit_time=datetime.utcnow(),
                        )
                        if existing.opened_at:
                            trade.duration_seconds = int(
                                (datetime.utcnow() - existing.opened_at).total_seconds()
                            )
                        session.add(trade)

                        logger.info(
                            f"Trade closed: {symbol} PnL=${pnl:.2f} ({pnl_pct:.2f}%)"
                        )

                await session.commit()

        except Exception as e:
            logger.error(f"Failed to update DB on fill for {symbol}: {e}")

        # Emit fill event
        try:
            await self.event_bus.emit_order_filled(
                order_id=order_info["id"],
                symbol=symbol,
                side=side,
                quantity=quantity,
                fill_price=fill_price,
                strategy_name=strategy_name,
            )
        except Exception as e:
            logger.error(f"Failed to emit fill event: {e}")

        # Broadcast via websocket
        try:
            from api.websocket import broadcast_new_trade
            await broadcast_new_trade(
                trade_id=order_info["id"],
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=fill_price,
                strategy=strategy_name,
            )
        except Exception:
            pass

    async def _on_terminal(self, order_info: Dict, status) -> None:
        """Handle cancelled/rejected/expired order."""
        try:
            session = await get_session()
            async with session:
                from sqlalchemy import update

                db_status = {
                    OrderStatus.CANCELLED: DBOrderStatus.CANCELLED,
                    OrderStatus.REJECTED: DBOrderStatus.REJECTED,
                    OrderStatus.EXPIRED: DBOrderStatus.EXPIRED,
                }.get(status.status, DBOrderStatus.CANCELLED)

                stmt = (
                    update(DBOrder)
                    .where(DBOrder.broker_order_id == order_info["id"])
                    .values(
                        status=db_status,
                        updated_at=datetime.utcnow(),
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update terminal order status: {e}")

    async def cancel_all(self) -> int:
        """Cancel all pending orders. Returns count cancelled."""
        cancelled = 0
        for pending in self.pending_orders[:]:
            broker = self.brokers.get(pending["broker"])
            if broker and isinstance(broker, BaseBroker) and broker.is_connected:
                try:
                    success = await broker.cancel_order(pending["id"])
                    if success:
                        cancelled += 1
                except Exception as e:
                    logger.error(f"Failed to cancel order {pending['id']}: {e}")

        self.pending_orders.clear()
        logger.info(f"Cancelled {cancelled} pending orders")
        return cancelled
