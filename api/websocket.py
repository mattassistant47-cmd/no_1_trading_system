"""
WebSocket handling for real-time updates.
Broadcasts portfolio updates, trades, signals, alerts, and system health.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set

from fastapi import APIRouter, WebSocketException, status, WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.subscriptions: dict[WebSocket, Set[str]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscriptions[websocket] = set()
        logger.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]
        logger.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def subscribe(self, websocket: WebSocket, channel: str):
        if websocket not in self.subscriptions:
            self.subscriptions[websocket] = set()
        self.subscriptions[websocket].add(channel)
        logger.debug(f"Client subscribed to {channel}")

    async def unsubscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.subscriptions:
            self.subscriptions[websocket].discard(channel)
            logger.debug(f"Client unsubscribed from {channel}")

    async def broadcast(self, channel: str, message: dict):
        """Broadcast message to all clients subscribed to channel."""
        disconnected = []

        for connection, channels in self.subscriptions.items():
            if channel in channels or channel == "system":
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Error sending to client: {e}")
                    disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast_all(self, message: dict):
        """Broadcast to all connected clients."""
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error sending to client: {e}")
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)


manager = ConnectionManager()


# Message models
class WebSocketMessage(BaseModel):
    type: str
    channel: str
    timestamp: datetime
    data: dict


class PortfolioUpdate(BaseModel):
    portfolio_value: float
    cash: float
    invested: float
    daily_pnl: float
    total_pnl: float
    daily_pnl_percentage: float


class TradeSignal(BaseModel):
    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    strategy: str
    timestamp: datetime


class RiskAlert(BaseModel):
    id: str
    severity: str
    message: str
    metric: str
    value: float
    threshold: float
    timestamp: datetime


class SystemAlert(BaseModel):
    component: str
    status: str
    message: str
    timestamp: datetime


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.

    Clients can subscribe to channels:
    - portfolio: Portfolio updates
    - trades: New trades and trade updates
    - signals: Strategy signals
    - alerts: Risk alerts
    - system: System health and status

    Message format:
    {
        "type": "subscribe|unsubscribe|ping",
        "channel": "portfolio|trades|signals|alerts|system",
        "data": {}
    }
    """
    try:
        await manager.connect(websocket)

        # Send welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "message": "Connected to trading system",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Handle incoming messages
        while True:
            try:
                # Wait for message with timeout
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)

                message_type = data.get("type", "").lower()
                channel = data.get("channel", "")

                if message_type == "subscribe":
                    if channel:
                        await manager.subscribe(websocket, channel)
                        await websocket.send_json(
                            {
                                "type": "subscription_confirmed",
                                "channel": channel,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )

                elif message_type == "unsubscribe":
                    if channel:
                        await manager.unsubscribe(websocket, channel)
                        await websocket.send_json(
                            {
                                "type": "unsubscription_confirmed",
                                "channel": channel,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        )

                elif message_type == "ping":
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Unknown message type: {message_type}",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await websocket.send_json(
                        {
                            "type": "heartbeat",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                except Exception:
                    break  # client disconnected

            except json.JSONDecodeError:
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Invalid JSON",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                except Exception:
                    break

            except Exception as e:
                # If it's a disconnect, just exit loop cleanly
                err_name = type(e).__name__
                if "Disconnect" in err_name or "ConnectionClosed" in err_name or "Abnormal" in str(e):
                    logger.debug(f"WebSocket disconnected: {err_name}")
                    break
                logger.warning(f"WebSocket message handling error: {e}")
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Internal server error",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                except Exception:
                    break

    except Exception as e:
        err_name = type(e).__name__
        if "Disconnect" not in err_name and "ConnectionClosed" not in err_name:
            logger.warning(f"WebSocket connection error: {err_name}: {e}")

    finally:
        manager.disconnect(websocket)


# Broadcast helper functions (called from other parts of the system)
async def broadcast_portfolio_update(
    portfolio_value: float,
    cash: float,
    invested: float,
    daily_pnl: float,
    total_pnl: float,
    daily_pnl_percentage: float,
):
    """Broadcast portfolio update to all subscribed clients."""
    message = {
        "type": "portfolio_update",
        "channel": "portfolio",
        "data": {
            "portfolio_value": portfolio_value,
            "cash": cash,
            "invested": invested,
            "daily_pnl": daily_pnl,
            "total_pnl": total_pnl,
            "daily_pnl_percentage": daily_pnl_percentage,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast("portfolio", message)


async def broadcast_new_trade(
    trade_id: str,
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    strategy: str,
):
    """Broadcast new trade signal to clients."""
    message = {
        "type": "new_trade",
        "channel": "trades",
        "data": {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "strategy": strategy,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast("trades", message)


async def broadcast_signal(
    strategy: str,
    symbol: str,
    signal_type: str,
    strength: float,
    data: dict = None,
):
    """Broadcast strategy signal to clients."""
    message = {
        "type": "signal",
        "channel": "signals",
        "data": {
            "strategy": strategy,
            "symbol": symbol,
            "signal_type": signal_type,
            "strength": strength,
            "signal_data": data or {},
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast("signals", message)


async def broadcast_risk_alert(
    severity: str,
    message: str,
    metric: str,
    value: float,
    threshold: float,
):
    """Broadcast risk alert to clients."""
    alert_message = {
        "type": "risk_alert",
        "channel": "alerts",
        "data": {
            "severity": severity,
            "message": message,
            "metric": metric,
            "value": value,
            "threshold": threshold,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast("alerts", alert_message)


async def broadcast_system_status(
    component: str,
    status: str,
    message: str = None,
):
    """Broadcast system status to all clients."""
    status_message = {
        "type": "system_status",
        "channel": "system",
        "data": {
            "component": component,
            "status": status,
            "message": message,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast_all(status_message)


async def broadcast_trade_closed(
    trade_id: str,
    symbol: str,
    exit_price: float,
    pnl: float,
    pnl_percentage: float,
):
    """Broadcast trade closure to clients."""
    message = {
        "type": "trade_closed",
        "channel": "trades",
        "data": {
            "trade_id": trade_id,
            "symbol": symbol,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_percentage": pnl_percentage,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast("trades", message)
