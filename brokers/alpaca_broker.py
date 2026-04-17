"""
Alpaca broker adapter for stocks and crypto trading.

Supports:
- Paper and live trading modes
- Stock trading with fractional shares
- Cryptocurrency trading (24/5)
- Options trading
- Real-time websocket streaming
- Proper rate limiting (200 calls/min)
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Callable, Dict, Any
from enum import Enum
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
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        GetOrdersRequest,
        OrderRequest,
        MarketOrderRequest,
        LimitOrderRequest,
        StopOrderRequest,
        StopLimitOrderRequest,
    )
    from alpaca.trading.enums import (
        OrderStatus as AlpacaOrderStatus,
        OrderSide as AlpacaOrderSide,
        TimeInForce as AlpacaTimeInForce,
        OrderType as AlpacaOrderType,
    )
    from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
    from alpaca.data.enums import Adjustment
    from alpaca.data.live import StockDataStream, CryptoDataStream
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-py not installed. Install with: pip install alpaca-py")


class AlpacaBroker(BaseBroker):
    """
    Alpaca broker implementation.

    Supports paper and live trading for stocks, crypto, and options.
    Implements real-time streaming via websocket with proper rate limiting.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str = "https://paper-api.alpaca.markets",
        paper_trading: bool = True,
        **config
    ):
        """
        Initialize Alpaca broker.

        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            base_url: Base URL (paper or live)
            paper_trading: Use paper trading mode
            **config: Additional configuration
        """
        if not ALPACA_AVAILABLE:
            raise RuntimeError("alpaca-py not installed")

        super().__init__("alpaca", **config)
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper_trading = paper_trading
        self.base_url = base_url
        self.client: Optional[TradingClient] = None
        self.stock_data_client: Optional[StockHistoricalDataClient] = None
        self.crypto_data_client: Optional[CryptoHistoricalDataClient] = None
        self.stock_stream: Optional[StockDataStream] = None
        self.crypto_stream: Optional[CryptoDataStream] = None

        self._rate_limiter = RateLimiter(max_calls=200, window_seconds=60)
        self._streaming_tasks: Dict[str, asyncio.Task] = {}

        logger.info(
            f"Initialized Alpaca broker: "
            f"paper_trading={paper_trading}, "
            f"base_url={base_url}"
        )

    @property
    def supports_options(self) -> bool:
        """Alpaca supports options trading."""
        return True

    @property
    def supports_crypto(self) -> bool:
        """Alpaca supports crypto trading."""
        return True

    async def connect(self) -> bool:
        """
        Establish connection to Alpaca API.

        Returns:
            True if connection successful
        """
        try:
            self.client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper_trading,
            )
            self.stock_data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
            self.crypto_data_client = CryptoHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )

            # Test connection
            account = self.client.get_account()
            self._connected = True
            logger.info(f"Connected to Alpaca. Account: {account.account_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        """Close streaming connections."""
        try:
            if self.stock_stream:
                await self.stock_stream.close()
            if self.crypto_stream:
                await self.crypto_stream.close()

            # Cancel streaming tasks
            for task in self._streaming_tasks.values():
                task.cancel()
            self._streaming_tasks.clear()

            self._connected = False
            logger.info("Disconnected from Alpaca")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting from Alpaca: {e}")
            return False

    async def get_account(self) -> Account:
        """Get account information."""
        await self._rate_limiter.wait()

        try:
            alpaca_account = self.client.get_account()
            return Account(
                account_id=alpaca_account.account_number,
                balance=float(alpaca_account.portfolio_value),
                buying_power=float(alpaca_account.buying_power),
                equity=float(alpaca_account.equity),
                cash=float(alpaca_account.cash),
                multiplier=1.0,
                account_type="paper" if self.paper_trading else "live",
                broker_name="alpaca",
            )
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            raise

    async def get_positions(self) -> List[Position]:
        """Get all open positions."""
        await self._rate_limiter.wait()

        try:
            alpaca_positions = self.client.get_all_positions()
            positions = []

            for ap in alpaca_positions:
                positions.append(
                    Position(
                        symbol=ap.symbol,
                        quantity=float(ap.qty),
                        avg_entry_price=float(ap.avg_entry_price),
                        current_price=float(ap.current_price),
                        market_value=float(ap.market_value),
                        unrealized_pl=float(ap.unrealized_pl),
                        unrealized_pl_pct=float(ap.unrealized_plpc),
                        position_type="long" if float(ap.qty) > 0 else "short",
                        asset_class="crypto" if "/" in ap.symbol else "stock",
                    )
                )

            logger.debug(f"Retrieved {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """Submit an order."""
        await self._validate_symbol(symbol)
        await self._validate_order_params(qty, order_type, limit_price, stop_price)
        await self._rate_limiter.wait()

        try:
            # Map our enums to Alpaca enums
            alpaca_side = (
                AlpacaOrderSide.BUY
                if side == OrderSide.BUY
                else AlpacaOrderSide.SELL
            )
            alpaca_tif = self._map_time_in_force(time_in_force)

            # Create order request based on type
            if order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                )
            elif order_type == OrderType.LIMIT:
                request = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    limit_price=limit_price,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                )
            elif order_type == OrderType.STOP:
                request = StopOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    stop_price=stop_price,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                )
            elif order_type == OrderType.STOP_LIMIT:
                request = StopLimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    limit_price=limit_price,
                    stop_price=stop_price,
                    side=alpaca_side,
                    time_in_force=alpaca_tif,
                )

            # Submit order
            alpaca_order = self.client.submit_order(request)

            order = Order(
                order_id=alpaca_order.id,
                symbol=alpaca_order.symbol,
                side=side,
                order_type=order_type,
                quantity=float(alpaca_order.qty),
                filled_quantity=float(alpaca_order.filled_qty),
                status=self._map_order_status(alpaca_order.status),
                limit_price=limit_price,
                stop_price=stop_price,
                time_in_force=time_in_force,
            )

            logger.info(
                f"Submitted {side.value} order: {symbol} x {qty} "
                f"(ID: {order.order_id})"
            )
            return order

        except Exception as e:
            logger.error(f"Failed to submit order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        await self._rate_limiter.wait()

        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Cancelled order: {order_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status."""
        await self._rate_limiter.wait()

        try:
            alpaca_order = self.client.get_order_by_id(order_id)
            return Order(
                order_id=alpaca_order.id,
                symbol=alpaca_order.symbol,
                side=(
                    OrderSide.BUY
                    if alpaca_order.side == AlpacaOrderSide.BUY
                    else OrderSide.SELL
                ),
                order_type=OrderType.MARKET,  # Simplified mapping
                quantity=float(alpaca_order.qty),
                filled_quantity=float(alpaca_order.filled_qty),
                status=self._map_order_status(alpaca_order.status),
                avg_fill_price=float(alpaca_order.filled_avg_price)
                    if alpaca_order.filled_avg_price else None,
            )
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise

    async def get_recent_filled_orders(self, limit: int = 50) -> list:
        """Get recent filled orders from Alpaca.

        Returns a list of dicts (not dataclasses) with the fields the
        dashboard needs: symbol, side, qty, entryPrice (filled avg),
        filled_at, strategy, asset_class.
        """
        await self._rate_limiter.wait()
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus, OrderStatus as AlpacaOrderStatus

            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=limit)
            orders = self.client.get_orders(filter=req)

            results = []
            for o in orders:
                if o.status != AlpacaOrderStatus.FILLED:
                    continue
                if not o.filled_avg_price or not o.filled_qty:
                    continue
                side_str = "BUY" if o.side == AlpacaOrderSide.BUY else "SELL"
                results.append({
                    "id": str(o.id),
                    "symbol": o.symbol,
                    "side": side_str,
                    "qty": float(o.filled_qty),
                    "entryPrice": float(o.filled_avg_price),
                    "exitPrice": 0.0,   # filled orders don't have an exit in Alpaca
                    "pnl": 0.0,         # realized PnL requires pairing open/close; left 0
                    "strategy": "manual",
                    "date": o.filled_at.isoformat() if o.filled_at else "",
                    "assetClass": str(getattr(o, "asset_class", "stock")),
                })
            return results
        except Exception as e:
            logger.error(f"Failed to get recent filled orders: {e}")
            return []

    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Get historical OHLCV data."""
        await self._validate_symbol(symbol)
        await self._rate_limiter.wait()

        try:
            is_crypto = "/" in symbol
            client = self.crypto_data_client if is_crypto else self.stock_data_client

            if is_crypto:
                request = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=self._map_timeframe(timeframe),
                    start=start,
                    end=end,
                    adjustment=Adjustment.ADJUSTED,
                )
            else:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=self._map_timeframe(timeframe),
                    start=start,
                    end=end,
                    adjustment=Adjustment.ADJUSTED,
                )

            bars = client.get_bar_data(request)
            df = bars[symbol].df

            logger.debug(
                f"Retrieved {len(df)} bars for {symbol} ({timeframe})"
            )
            return df

        except Exception as e:
            logger.error(f"Failed to get historical bars: {e}")
            raise

    async def stream_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], None],
    ) -> None:
        """Stream real-time quotes."""
        try:
            # Separate stocks and crypto
            stocks = [s for s in symbols if "/" not in s]
            crypto = [s for s in symbols if "/" in s]

            # Stream stocks if any
            if stocks:
                if not self.stock_stream:
                    self.stock_stream = StockDataStream(
                        api_key=self.api_key,
                        secret_key=self.secret_key,
                    )

                async with self.stock_stream as stream:
                    # Subscribe to updates
                    await stream.subscribe_quotes(*stocks)

                    async for quote in stream:
                        quote_obj = Quote(
                            symbol=quote.symbol,
                            bid=float(quote.bid_price),
                            ask=float(quote.ask_price),
                            bid_size=float(quote.bid_size),
                            ask_size=float(quote.ask_size),
                            last_price=float(quote.bid_price),  # Use bid as proxy
                            last_size=float(quote.bid_size),
                            timestamp=datetime.fromtimestamp(
                                quote.timestamp / 1e9
                            ),
                        )
                        if asyncio.iscoroutinefunction(callback):
                            await callback(quote_obj)
                        else:
                            callback(quote_obj)

            # Stream crypto if any
            if crypto:
                if not self.crypto_stream:
                    self.crypto_stream = CryptoDataStream(
                        api_key=self.api_key,
                        secret_key=self.secret_key,
                    )

                async with self.crypto_stream as stream:
                    await stream.subscribe_quotes(*crypto)

                    async for quote in stream:
                        quote_obj = Quote(
                            symbol=quote.symbol,
                            bid=float(quote.bid_price),
                            ask=float(quote.ask_price),
                            bid_size=float(quote.bid_size),
                            ask_size=float(quote.ask_size),
                            last_price=float(quote.bid_price),
                            last_size=float(quote.bid_size),
                            timestamp=datetime.fromtimestamp(
                                quote.timestamp / 1e9
                            ),
                        )
                        if asyncio.iscoroutinefunction(callback):
                            await callback(quote_obj)
                        else:
                            callback(quote_obj)

        except Exception as e:
            logger.error(f"Error streaming quotes: {e}")
            raise

    # Helper methods
    def _map_time_in_force(self, tif: TimeInForce) -> AlpacaTimeInForce:
        """Map TimeInForce enum to Alpaca enum."""
        mapping = {
            TimeInForce.DAY: AlpacaTimeInForce.DAY,
            TimeInForce.GTC: AlpacaTimeInForce.GTC,
            TimeInForce.OPG: AlpacaTimeInForce.OPG,
            TimeInForce.CLS: AlpacaTimeInForce.CLS,
            TimeInForce.IOC: AlpacaTimeInForce.IOC,
            TimeInForce.FOK: AlpacaTimeInForce.FOK,
        }
        return mapping.get(tif, AlpacaTimeInForce.DAY)

    def _map_order_status(self, status: AlpacaOrderStatus) -> OrderStatus:
        """Map Alpaca order status to our enum."""
        mapping = {
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.OPEN,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.PENDING_CANCEL: OrderStatus.PENDING,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.EXPIRED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
        }
        return mapping.get(status, OrderStatus.PENDING)

    def _map_timeframe(self, timeframe: str):
        """Map timeframe string to Alpaca TimeFrame."""
        from alpaca.data.enums import TimeFrame

        mapping = {
            "1min": TimeFrame.MINUTE,
            "5min": TimeFrame(5),
            "15min": TimeFrame(15),
            "30min": TimeFrame(30),
            "1h": TimeFrame.HOUR,
            "1d": TimeFrame.DAY,
            "1w": TimeFrame.WEEK,
        }
        return mapping.get(timeframe, TimeFrame.HOUR)


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, max_calls: int, window_seconds: int):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum calls per window
            window_seconds: Window duration in seconds
        """
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: List[datetime] = []

    async def wait(self) -> None:
        """Wait until next call is allowed."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # Remove old calls outside the window
        self.calls = [c for c in self.calls if c > cutoff]

        # Check if we've hit the limit
        if len(self.calls) >= self.max_calls:
            sleep_time = (self.calls[0] - cutoff).total_seconds()
            logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time + 0.1)

        self.calls.append(now)


__all__ = ["AlpacaBroker"]
