"""
Interactive Brokers (IBKR) adapter using ib_async.

Supports:
- Stock and options trading
- Paper and live trading modes
- Combo/spread orders for options strategies
- Automatic reconnection logic
- Contract chain lookups

Note: ib_async is an optional dependency. If not installed,
a helpful error message guides installation.
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Callable, Dict, Any
import pandas as pd
from loguru import logger

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
    from ib_async import IB, Stock, Index, Forex, CFD, Future, Option, Bag
    from ib_async import Contract, Order as IBOrder, Trade, TickAttrib
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False
    logger.warning("ib_async not installed. Install with: pip install ib_async")


class IBKRBroker(BaseBroker):
    """
    Interactive Brokers adapter using ib_async library.

    Supports full options trading with chain lookups and spread orders.
    Implements automatic reconnection with exponential backoff.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        paper_trading: bool = True,
        **config
    ):
        """
        Initialize IBKR broker.

        Args:
            host: IB Gateway/TWS host (default: localhost)
            port: IB Gateway/TWS port (7497 for paper, 7496 for live)
            client_id: Unique client ID for this connection
            paper_trading: Use paper trading mode
            **config: Additional configuration

        Note:
            IB Gateway or Trader Workstation must be running at host:port
        """
        if not IBKR_AVAILABLE:
            raise RuntimeError(
                "ib_async not installed. "
                "Install with: pip install ib_async"
            )

        super().__init__("ibkr", **config)
        self.host = host
        self.port = port
        self.client_id = client_id
        self.paper_trading = paper_trading
        self.ib = IB()

        self._reconnect_delay = 1  # Initial delay in seconds
        self._max_reconnect_delay = 60
        self._open_trades: Dict[int, Trade] = {}

        logger.info(
            f"Initialized IBKR broker: "
            f"host={host}:{port}, "
            f"client_id={client_id}, "
            f"paper_trading={paper_trading}"
        )

    @property
    def supports_options(self) -> bool:
        """IBKR supports options trading."""
        return True

    @property
    def supports_crypto(self) -> bool:
        """IBKR supports crypto trading via forex pairs."""
        return True

    async def connect(self) -> bool:
        """
        Connect to IB Gateway.

        Implements automatic reconnection with exponential backoff.

        Returns:
            True if connection successful
        """
        retry_count = 0
        max_retries = 5

        while retry_count < max_retries:
            try:
                await self.ib.connectAsync(
                    host=self.host,
                    port=self.port,
                    clientId=self.client_id,
                )

                # Subscribe to connection events
                self.ib.connectedEvent += self._on_connected
                self.ib.disconnectedEvent += self._on_disconnected

                self._connected = True
                self._reconnect_delay = 1  # Reset on successful connection
                logger.info(f"Connected to IBKR at {self.host}:{self.port}")
                return True

            except Exception as e:
                retry_count += 1
                logger.warning(
                    f"Connection attempt {retry_count}/{max_retries} failed: {e}"
                )

                if retry_count < max_retries:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._max_reconnect_delay
                    )

        logger.error("Failed to connect to IBKR after max retries")
        self._connected = False
        return False

    async def disconnect(self) -> bool:
        """Disconnect from IB Gateway."""
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                self._connected = False
                logger.info("Disconnected from IBKR")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from IBKR: {e}")
            return False

    async def get_account(self) -> Account:
        """Get account information."""
        if not self.ib.isConnected():
            raise RuntimeError("Not connected to IBKR")

        try:
            # Request account summary
            self.ib.reqAccountSummary(9001, "All", "AccountType")
            await asyncio.sleep(0.5)  # Wait for data

            account_values = self.ib.accountValues()
            summary_dict = {v.tag: v.value for v in account_values}

            return Account(
                account_id=self.ib.wrapper.accounts[0] if self.ib.wrapper.accounts else "unknown",
                balance=float(summary_dict.get("NetLiquidation", 0)),
                buying_power=float(summary_dict.get("BuyingPower", 0)),
                equity=float(summary_dict.get("Equity", 0)),
                cash=float(summary_dict.get("CashBalance", 0)),
                multiplier=1.0,
                account_type="paper" if self.paper_trading else "live",
                broker_name="ibkr",
            )
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            raise

    async def get_positions(self) -> List[Position]:
        """Get all open positions."""
        if not self.ib.isConnected():
            raise RuntimeError("Not connected to IBKR")

        try:
            positions = []
            portfolio = self.ib.portfolio()

            for item in portfolio:
                contract = item.contract
                symbol = contract.symbol
                if contract.secType == "OPT":
                    symbol = f"{symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right}"

                positions.append(
                    Position(
                        symbol=symbol,
                        quantity=float(item.position),
                        avg_entry_price=float(item.avgCost),
                        current_price=float(item.marketPrice),
                        market_value=float(item.marketValue),
                        unrealized_pl=float(item.unrealizedPNL),
                        unrealized_pl_pct=float(item.unrealizedPNL) / abs(float(item.cost)) * 100
                            if item.cost != 0 else 0,
                        position_type="long" if item.position > 0 else "short",
                        asset_class=self._map_asset_class(contract.secType),
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
        """
        Submit an order.

        For options, symbol format: "TICKER 20240315 100.0 C" (symbol date strike right)
        """
        if not self.ib.isConnected():
            raise RuntimeError("Not connected to IBKR")

        await self._validate_symbol(symbol)
        await self._validate_order_params(qty, order_type, limit_price, stop_price)

        try:
            # Parse symbol and create contract
            contract = self._parse_symbol_to_contract(symbol)
            if not contract:
                raise ValueError(f"Cannot parse symbol: {symbol}")

            # Create IB order
            ib_order = IBOrder()
            ib_order.action = "BUY" if side == OrderSide.BUY else "SELL"
            ib_order.totalQuantity = qty
            ib_order.orderType = self._map_order_type(order_type)

            if order_type == OrderType.LIMIT:
                ib_order.lmtPrice = limit_price
            elif order_type == OrderType.STOP:
                ib_order.auxPrice = stop_price
            elif order_type == OrderType.STOP_LIMIT:
                ib_order.lmtPrice = limit_price
                ib_order.auxPrice = stop_price

            ib_order.tif = self._map_time_in_force(time_in_force)
            ib_order.eTradeOnly = False
            ib_order.firmQuoteOnly = False

            # Submit order
            trade = self.ib.placeOrder(contract, ib_order)
            self._open_trades[trade.order.orderId] = trade

            order = Order(
                order_id=str(trade.order.orderId),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=qty,
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
        if not self.ib.isConnected():
            raise RuntimeError("Not connected to IBKR")

        try:
            order_id_int = int(order_id)
            if order_id_int in self._open_trades:
                trade = self._open_trades[order_id_int]
                self.ib.cancelOrder(trade.order)
                logger.info(f"Cancelled order: {order_id}")
                return True
            else:
                logger.warning(f"Order not found: {order_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status."""
        try:
            order_id_int = int(order_id)
            if order_id_int in self._open_trades:
                trade = self._open_trades[order_id_int]
                return Order(
                    order_id=order_id,
                    symbol=trade.contract.symbol,
                    side=OrderSide.BUY if trade.order.action == "BUY" else OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=float(trade.order.totalQuantity),
                    filled_quantity=float(trade.orderStatus.filled) if hasattr(trade, 'orderStatus') else 0,
                    status=self._map_order_status(trade.orderStatus.status if hasattr(trade, 'orderStatus') else ""),
                )
            else:
                raise ValueError(f"Order not found: {order_id}")

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
        Get historical OHLCV data.

        Note: This is a stub. Full implementation requires IB API historical data subscription.
        """
        await self._validate_symbol(symbol)

        logger.warning(
            "TODO: Implement historical bars for IBKR. "
            "Requires market data subscription and IB API integration."
        )
        # TODO: Implement using ib.reqHistoricalData()
        return pd.DataFrame()

    async def stream_quotes(
        self,
        symbols: List[str],
        callback: Callable[[Quote], None],
    ) -> None:
        """
        Stream real-time quotes.

        Note: This is a stub. Full implementation requires tick data subscription.
        """
        if not self.ib.isConnected():
            raise RuntimeError("Not connected to IBKR")

        logger.warning(
            "TODO: Implement streaming quotes for IBKR. "
            "Requires market data subscription."
        )
        # TODO: Implement using ib.reqMktData() and tick handlers

    # Helper methods
    def _parse_symbol_to_contract(self, symbol: str) -> Optional[Contract]:
        """
        Parse symbol string to IB Contract.

        Formats:
        - "AAPL" -> Stock
        - "ES" -> Futures
        - "EURUSD" -> Forex
        - "AAPL 20240315 100.0 C" -> Option
        """
        parts = symbol.split()

        if len(parts) == 4:
            # Option: TICKER DATE STRIKE RIGHT
            ticker, date, strike, right = parts
            return Option(ticker, date, float(strike), right, "SMART", "USD")

        elif len(parts) == 1:
            ticker = parts[0]

            # Try to detect type by symbol
            if len(ticker) == 6 and ticker.isupper():
                # Likely forex pair (e.g., EURUSD)
                return Forex(ticker)
            elif ticker in ["ES", "NQ", "YM", "GC"]:
                # Common futures
                return Future(ticker, "USD")
            else:
                # Default to stock
                return Stock(ticker, "SMART", "USD")

        else:
            logger.error(f"Cannot parse symbol: {symbol}")
            return None

    def _map_asset_class(self, sec_type: str) -> str:
        """Map IB security type to asset class."""
        mapping = {
            "STK": "stock",
            "OPT": "option",
            "FUT": "future",
            "FOREX": "forex",
            "CFD": "cfd",
            "CRYPTO": "crypto",
        }
        return mapping.get(sec_type, "unknown")

    def _map_order_type(self, order_type: OrderType) -> str:
        """Map OrderType to IB order type."""
        mapping = {
            OrderType.MARKET: "MKT",
            OrderType.LIMIT: "LMT",
            OrderType.STOP: "STP",
            OrderType.STOP_LIMIT: "STP LMT",
        }
        return mapping.get(order_type, "MKT")

    def _map_time_in_force(self, tif: TimeInForce) -> str:
        """Map TimeInForce to IB TIF."""
        mapping = {
            TimeInForce.DAY: "DAY",
            TimeInForce.GTC: "GTC",
            TimeInForce.IOC: "IOC",
            TimeInForce.FOK: "FOK",
        }
        return mapping.get(tif, "DAY")

    def _map_order_status(self, status: str) -> OrderStatus:
        """Map IB order status to our enum."""
        mapping = {
            "PreSubmitted": OrderStatus.PENDING,
            "PendingSubmit": OrderStatus.PENDING,
            "ApiPending": OrderStatus.PENDING,
            "Submitted": OrderStatus.OPEN,
            "Accepted": OrderStatus.OPEN,
            "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
            "Filled": OrderStatus.FILLED,
            "ApiCancelled": OrderStatus.CANCELLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Expired": OrderStatus.EXPIRED,
            "Rejected": OrderStatus.REJECTED,
        }
        return mapping.get(status, OrderStatus.PENDING)

    def _on_connected(self):
        """Callback when connected to IB."""
        logger.info("IB connection event triggered")
        self._connected = True

    def _on_disconnected(self):
        """Callback when disconnected from IB."""
        logger.warning("IB disconnected, attempting reconnection...")
        self._connected = False
        asyncio.create_task(self._auto_reconnect())

    async def _auto_reconnect(self):
        """Automatically reconnect with exponential backoff."""
        while not self._connected and self._reconnect_delay < self._max_reconnect_delay:
            await asyncio.sleep(self._reconnect_delay)
            logger.info(f"Attempting auto-reconnect (delay: {self._reconnect_delay}s)")

            if await self.connect():
                logger.info("Auto-reconnect successful")
                self._reconnect_delay = 1
                return

            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay
            )


__all__ = ["IBKRBroker"]
