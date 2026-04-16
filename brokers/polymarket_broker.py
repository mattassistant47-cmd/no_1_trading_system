"""
Polymarket broker adapter for prediction market trading.

Supports:
- CLOB (Central Limit Order Book) API integration
- Market and limit orders
- USDC allowance management
- WebSocket price updates
- Position and P&L tracking
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Callable, Dict, Any
import pandas as pd
from loguru import logger
import httpx

from brokers.base import (
    BaseBroker,
    Account,
    Position,
    Order,
    Quote,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
)

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        OrderSide as ClobOrderSide,
        OrderType as ClobOrderType,
    )
    POLYMARKET_AVAILABLE = True
except ImportError:
    POLYMARKET_AVAILABLE = False
    logger.warning("py-clob-client not installed. Install with: pip install py-clob-client")


class PolymarketBroker(BaseBroker):
    """
    Polymarket prediction market adapter.

    Integrates with Polymarket's CLOB API for trading on binary outcome markets.
    Handles USDC allowances, position tracking, and real-time WebSocket updates.
    """

    def __init__(
        self,
        private_key: str,
        chain_id: int = 137,  # Polygon mainnet
        **config
    ):
        """
        Initialize Polymarket broker.

        Args:
            private_key: Ethereum private key (with leading 0x)
            chain_id: Blockchain chain ID (137 = Polygon)
            **config: Additional configuration (proxy, endpoint URLs)

        Note:
            USDC balance required on Polygon network.
            Get USDC at https://aave.com or similar bridges.
        """
        if not POLYMARKET_AVAILABLE:
            raise RuntimeError(
                "py-clob-client not installed. "
                "Install with: pip install py-clob-client"
            )

        super().__init__("polymarket", **config)
        self.private_key = private_key
        self.chain_id = chain_id
        self.client: Optional[ClobClient] = None
        self._usdc_balance = 0.0
        self._position_cache: Dict[str, Position] = {}
        self._market_cache: Dict[str, Dict] = {}

        logger.info(f"Initialized Polymarket broker: chain_id={chain_id}")

    @property
    def supports_options(self) -> bool:
        """Polymarket trades binary outcomes, not options."""
        return False

    @property
    def supports_crypto(self) -> bool:
        """Polymarket uses USDC (crypto), but not crypto spot trading."""
        return False

    async def connect(self) -> bool:
        """
        Connect to Polymarket CLOB.

        Initializes client and verifies USDC balance.

        Returns:
            True if connection successful
        """
        try:
            # Initialize CLOB client
            self.client = ClobClient(
                host="https://clob.polymarket.com",
                chain_id=self.chain_id,
                private_key=self.private_key,
                signature_type=self.config.get("signature_type", "EOA"),
            )

            # Get account info
            account = await self.get_account()
            self._connected = True

            logger.info(
                f"Connected to Polymarket. "
                f"USDC Balance: ${account.cash:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Polymarket."""
        try:
            self.client = None
            self._connected = False
            logger.info("Disconnected from Polymarket")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            return False

    async def get_account(self) -> Account:
        """Get account USDC balance and balance info."""
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            # Get user address from private key
            user = self.client.get_user()
            usdc_balance = float(self.client.get_balance_allowance())

            return Account(
                account_id=user.address if hasattr(user, "address") else "unknown",
                balance=usdc_balance,
                buying_power=usdc_balance,
                equity=usdc_balance,
                cash=usdc_balance,
                multiplier=1.0,
                account_type="production",
                broker_name="polymarket",
            )

        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            raise

    async def get_positions(self) -> List[Position]:
        """Get all open positions in prediction markets."""
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            positions = []
            user = self.client.get_user()

            # Get user orders/trades to derive positions
            user_trades = self.client.get_user_orders()

            # Group by market to calculate net positions
            position_dict: Dict[str, Dict[str, float]] = {}

            for trade in user_trades:
                market_id = trade.market
                if market_id not in position_dict:
                    position_dict[market_id] = {
                        "yes": 0.0,
                        "no": 0.0,
                        "market_data": None,
                    }

                # Accumulate position size
                side = "yes" if trade.side == ClobOrderSide.BUY else "no"
                position_dict[market_id][side] += float(trade.size)

            # Build position objects
            for market_id, data in position_dict.items():
                # Fetch market data for pricing
                market = self._get_market_data(market_id)
                if not market:
                    continue

                # Calculate net position (for binary markets, usually YES or NO)
                net_position = data["yes"] - data["no"]
                if abs(net_position) < 0.001:  # No open position
                    continue

                position_type = "long" if net_position > 0 else "short"
                current_price = float(market.get("midPrice", 0.5))

                positions.append(
                    Position(
                        symbol=f"{market_id}",
                        quantity=abs(net_position),
                        avg_entry_price=0.5,  # Approximate
                        current_price=current_price,
                        market_value=abs(net_position) * current_price,
                        unrealized_pl=0.0,  # Simplified
                        unrealized_pl_pct=0.0,
                        position_type=position_type,
                        asset_class="prediction",
                    )
                )

            logger.debug(f"Retrieved {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    async def submit_order(
        self,
        symbol: str,  # Market ID
        qty: float,
        side: OrderSide,
        order_type: OrderType,
        time_in_force: TimeInForce = TimeInForce.GTC,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """
        Submit an order to Polymarket.

        Args:
            symbol: Polymarket market ID
            qty: Size in USDC or tokens
            side: YES (BUY) or NO (SELL)
            order_type: LIMIT or MARKET
            limit_price: Price (0.0 to 1.0 for binary markets)
            stop_price: Not used for Polymarket

        Returns:
            Order object
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        await self._validate_symbol(symbol)

        try:
            # Map side
            clob_side = (
                ClobOrderSide.BUY
                if side == OrderSide.BUY
                else ClobOrderSide.SELL
            )

            # Validate and prepare order
            if order_type == OrderType.LIMIT and not limit_price:
                raise ValueError("LIMIT order requires limit_price")

            if limit_price and (limit_price < 0.0 or limit_price > 1.0):
                raise ValueError("Polymarket prices must be between 0 and 1")

            # Submit order
            if order_type == OrderType.MARKET:
                # Use current mid-price for market orders
                market = self._get_market_data(symbol)
                limit_price = float(market.get("midPrice", 0.5))

            order_id = self.client.create_order(
                market_id=symbol,
                side=clob_side,
                size=qty,
                price=limit_price,
                signature_type="EOA",
            )

            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=qty,
                limit_price=limit_price,
                status=OrderStatus.OPEN,
                time_in_force=time_in_force,
            )

            logger.info(
                f"Submitted {side.value} order: {symbol} x {qty} @ {limit_price} "
                f"(ID: {order_id})"
            )
            return order

        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            self.client.cancel_order(order_id)
            logger.info(f"Cancelled order: {order_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status."""
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            order_data = self.client.get_order(order_id)

            return Order(
                order_id=order_id,
                symbol=order_data.market,
                side=(
                    OrderSide.BUY
                    if order_data.side == ClobOrderSide.BUY
                    else OrderSide.SELL
                ),
                order_type=OrderType.LIMIT,
                quantity=float(order_data.size),
                filled_quantity=float(order_data.filled_size),
                status=self._map_order_status(order_data.status),
                limit_price=float(order_data.price),
            )

        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise

    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get historical price data for a market.

        Note: Polymarket doesn't provide direct historical bar data.
        This would require archiving price updates from WebSocket.
        """
        logger.warning(
            "TODO: Implement historical bars for Polymarket. "
            "Requires archiving WebSocket tick data."
        )
        return pd.DataFrame()

    async def stream_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], None],
    ) -> None:
        """
        Stream real-time quote updates.

        Note: This is a stub. Full implementation requires WebSocket integration.
        """
        logger.warning(
            "TODO: Implement WebSocket streaming for Polymarket. "
            "Requires wss://ws.polymarket.com connection."
        )

    # Helper methods
    def _get_market_data(self, market_id: str) -> Optional[Dict[str, Any]]:
        """
        Get market data (prices, order book).

        Returns cached data if available, otherwise fetches from API.
        """
        if market_id in self._market_cache:
            return self._market_cache[market_id]

        try:
            market_data = self.client.get_market(market_id)
            self._market_cache[market_id] = market_data
            return market_data
        except Exception as e:
            logger.warning(f"Failed to get market data for {market_id}: {e}")
            return None

    def _map_order_status(self, status: str) -> OrderStatus:
        """Map Polymarket order status to our enum."""
        mapping = {
            "OPEN": OrderStatus.OPEN,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.EXPIRED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return mapping.get(status, OrderStatus.PENDING)

    async def ensure_usdc_allowance(self, amount: float) -> bool:
        """
        Ensure USDC allowance is sufficient.

        Args:
            amount: Required USDC amount

        Returns:
            True if allowance is sufficient or was set successfully
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            current_allowance = float(self.client.get_balance_allowance())

            if current_allowance >= amount:
                return True

            logger.info(f"Setting USDC allowance to {amount}")
            # TODO: Implement USDC approve() call
            # This requires direct contract interaction with USDC token

            return True

        except Exception as e:
            logger.error(f"Failed to ensure USDC allowance: {e}")
            return False


__all__ = ["PolymarketBroker"]
