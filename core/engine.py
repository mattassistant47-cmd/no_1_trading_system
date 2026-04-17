"""
Main trading engine orchestrating all system components.
Handles broker initialization, strategy execution, and graceful shutdown.
"""

import asyncio
import signal
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.settings import settings
from core.database import DatabaseManager, init_db, get_session
from core.events import event_bus, EventType, Event
from core.models import (
    Order as DBOrder,
    Trade as DBTrade,
    Position as DBPosition,
    PortfolioSnapshot,
    Signal as DBSignal,
    SystemLog,
    OrderStatus as DBOrderStatus,
    OrderSide as DBOrderSide,
    SignalType,
    PositionStatus,
    TradeType,
)


class TradingEngine:
    """Main trading engine coordinating all components."""

    def __init__(self) -> None:
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.running = False
        self.start_time: Optional[datetime] = None
        self.strategies: Dict[str, any] = {}
        self.brokers: Dict[str, any] = {}
        self.risk_manager: Optional[any] = None
        self.position_sizer: Optional[any] = None
        self.circuit_breaker: Optional[any] = None
        self.data_feed: Optional[any] = None
        self.order_executor: Optional[any] = None
        self.position_manager: Optional[any] = None

        # Portfolio state
        self._portfolio_value: float = settings.trading.initial_capital
        self._cash: float = settings.trading.initial_capital
        self._positions_value: float = 0.0
        self._daily_pnl: float = 0.0
        self._total_pnl: float = 0.0
        self._initial_capital: float = settings.trading.initial_capital
        self._open_positions: list = []
        self._market_data: Dict[str, any] = {}

        try:
            log_path = getattr(settings.logging, 'log_file_path', '/app/logs/trading.log')
            logger.add(
                log_path,
                rotation=f"{getattr(settings.logging, 'max_log_size_mb', 50)} MB",
                retention=f"{getattr(settings.logging, 'log_retention_days', 30)} days",
                level=getattr(settings.logging, 'level', 'INFO'),
            )
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not add file logger: {e}")

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def portfolio_value(self) -> float:
        return self._portfolio_value

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def total_pnl(self) -> float:
        return self._total_pnl

    @property
    def total_pnl_percentage(self) -> float:
        if self._initial_capital > 0:
            return (self._total_pnl / self._initial_capital) * 100
        return 0.0

    @property
    def initial_capital(self) -> float:
        return self._initial_capital

    @property
    def win_rate(self) -> float:
        for name, strategy in self.strategies.items():
            try:
                from strategies.base import BaseStrategy
                if isinstance(strategy, BaseStrategy):
                    return strategy.metrics.win_rate
            except Exception:
                pass
        return 0.0

    @property
    def sharpe_ratio(self) -> float:
        for name, strategy in self.strategies.items():
            try:
                from strategies.base import BaseStrategy
                if isinstance(strategy, BaseStrategy):
                    return strategy.metrics.sharpe_ratio
            except Exception:
                pass
        return 0.0

    @property
    def annual_return(self) -> float:
        return 0.0

    @property
    def max_drawdown(self) -> float:
        if self.risk_manager:
            try:
                from risk.manager import RiskManager
                if isinstance(self.risk_manager, RiskManager):
                    drawdown = (self.risk_manager.peak_equity - self.risk_manager.current_equity)
                    if self.risk_manager.peak_equity > 0:
                        return (drawdown / self.risk_manager.peak_equity) * 100
            except Exception:
                pass
        return 0.0

    @property
    def profit_factor(self) -> float:
        for name, strategy in self.strategies.items():
            try:
                from strategies.base import BaseStrategy
                if isinstance(strategy, BaseStrategy):
                    return strategy.metrics.profit_factor
            except Exception:
                pass
        return 0.0

    @property
    def avg_trade_duration_hours(self) -> float:
        return 0.0

    @property
    def open_positions(self) -> list:
        return self._open_positions

    @property
    def trading_mode(self) -> str:
        return settings.mode

    # ── Initialization ──────────────────────────────────────────────────

    async def initialize(self) -> None:
        logger.info("=" * 80)
        logger.info(f"Initializing {settings.app_name} v1.0.0")
        logger.info(f"Mode: {settings.mode.upper()}")
        logger.info(f"Environment: {settings.environment}")
        logger.info("=" * 80)

        try:
            logger.info("Setting up database...")
            await DatabaseManager.init()
            await init_db()
            logger.info("Database initialized successfully")

            logger.info("Connecting event bus...")
            await event_bus.connect()
            logger.info("Event bus connected")

            await self._initialize_brokers()
            await self._initialize_strategies()
            await self._initialize_risk_manager()
            await self._initialize_data_feed()
            await self._initialize_order_executor()
            await self._setup_scheduler()

            # Backfill Alpaca order history into DB
            try:
                await self._backfill_alpaca_orders()
            except Exception as e:
                logger.warning(f"Alpaca backfill failed: {e}")

            # Wire event bus subscribers
            event_bus.subscribe(EventType.SIGNAL_GENERATED, self._handle_signal_event)
            event_bus.subscribe(EventType.ORDER_FILLED, self._handle_fill_event)
            event_bus.subscribe(EventType.RISK_ALERT, self._handle_risk_alert)

            # Start background tasks instead of APScheduler
            self._background_tasks = []
            self.running = True
            self._start_background_tasks()
            logger.info("Background tasks started")

            # Trigger initial snapshot immediately
            try:
                asyncio.create_task(self._take_portfolio_snapshot())
            except Exception as e:
                logger.debug(f"Initial snapshot failed: {e}")

            logger.info("Trading engine initialization complete")
            self.start_time = datetime.utcnow()

        except Exception as e:
            logger.error(f"Initialization error: {e}", exc_info=True)
            raise

    async def _initialize_brokers(self) -> None:
        logger.info("Initializing brokers...")

        # Alpaca broker
        try:
            from brokers.alpaca_broker import AlpacaBroker
            api_key, api_secret, base_url = settings.get_alpaca_credentials()
            paper = settings.mode == "paper"

            broker = AlpacaBroker(
                api_key=api_key,
                secret_key=api_secret,
                base_url=base_url,
                paper_trading=paper,
            )
            connected = await broker.connect()
            if connected:
                self.brokers["alpaca"] = broker
                logger.info(f"Alpaca broker connected (Mode: {settings.mode})")
            else:
                logger.warning(
                    "Alpaca broker connection failed - continuing in degraded mode"
                )
                self.brokers["alpaca"] = broker  # keep for later retry
        except Exception as e:
            logger.warning(f"Could not initialize Alpaca broker: {e} - paper mode will use cached/mock data")

        # IBKR (if configured)
        if settings.ibkr.account_id:
            logger.info("Interactive Brokers configured (placeholder)")
            self.brokers["ibkr"] = {
                "account_id": settings.ibkr.account_id,
                "host": settings.ibkr.host,
                "port": settings.ibkr.port,
                "client_id": settings.ibkr.client_id,
            }

        # Polymarket (if configured)
        if settings.polymarket.api_key:
            logger.info("Polymarket configured (placeholder)")
            self.brokers["polymarket"] = {
                "api_key": settings.polymarket.api_key,
                "base_url": settings.polymarket.base_url,
            }

        logger.info(f"Brokers initialized: {list(self.brokers.keys())}")

    async def _initialize_strategies(self) -> None:
        logger.info("Initializing strategies...")

        from strategies import (
            MultiTimeframeMomentum,
            StatisticalMeanReversion,
            CryptoMomentum,
            OptionsWheel,
            PolymarketArbitrage,
            EnsembleStrategy,
            Breakout,
            TrendFollowing,
            PairsTrading,
            VolatilityRegime,
        )

        enabled = settings.get_enabled_strategies()

        if enabled["momentum"]:
            try:
                config = {
                    "enabled": True,
                    "asset_class": "equities",
                    "timeframe": "1D",
                    "weight": settings.momentum.allocation_weight,
                    "lookback": settings.momentum.lookback,
                    "threshold": settings.momentum.threshold,
                }
                self.strategies["momentum"] = MultiTimeframeMomentum(config)
                logger.info(
                    f"Momentum strategy enabled "
                    f"(lookback: {settings.momentum.lookback}, "
                    f"threshold: {settings.momentum.threshold})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize momentum strategy: {e}")

        if enabled["mean_reversion"]:
            try:
                config = {
                    "enabled": True,
                    "asset_class": "equities",
                    "timeframe": "1D",
                    "weight": settings.mean_reversion.allocation_weight,
                    "z_score_entry": settings.mean_reversion.z_score,
                    "lookback_period": settings.mean_reversion.window,
                }
                self.strategies["mean_reversion"] = StatisticalMeanReversion(config)
                logger.info(
                    f"Mean reversion strategy enabled "
                    f"(z_score: {settings.mean_reversion.z_score}, "
                    f"window: {settings.mean_reversion.window})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize mean reversion strategy: {e}")

        if enabled["crypto_momentum"]:
            try:
                config = {
                    "enabled": True,
                    "asset_class": "crypto",
                    "timeframe": "4H",
                    "weight": settings.crypto_momentum.allocation_weight,
                    "lookback": settings.crypto_momentum.lookback,
                }
                self.strategies["crypto_momentum"] = CryptoMomentum(config)
                logger.info(f"Crypto momentum strategy enabled")
            except Exception as e:
                logger.error(f"Failed to initialize crypto momentum strategy: {e}")

        if enabled["options_wheel"]:
            try:
                config = {
                    "enabled": True,
                    "asset_class": "options",
                    "weight": settings.options_wheel.allocation_weight,
                    "target_yield": settings.options_wheel.target_yield_percent,
                }
                self.strategies["options_wheel"] = OptionsWheel(config)
                logger.info(f"Options wheel strategy enabled")
            except Exception as e:
                logger.error(f"Failed to initialize options wheel strategy: {e}")

        if enabled["polymarket"]:
            try:
                config = {
                    "enabled": True,
                    "asset_class": "prediction_market",
                    "weight": settings.polymarket_strategy.allocation_weight,
                    "confidence_threshold": settings.polymarket_strategy.confidence_threshold,
                }
                self.strategies["polymarket"] = PolymarketArbitrage(config)
                logger.info("Polymarket strategy enabled")
            except Exception as e:
                logger.error(f"Failed to initialize polymarket strategy: {e}")

        if enabled.get("breakout"):
            try:
                config = {
                    "enabled": True,
                    "asset_class": "equities",
                    "timeframe": "1D",
                    "weight": settings.breakout.allocation_weight,
                    "lookback": settings.breakout.lookback,
                    "atr_multiplier": settings.breakout.atr_multiplier,
                    "volume_confirmation": settings.breakout.volume_confirmation,
                }
                self.strategies["breakout"] = Breakout(config)
                logger.info(
                    f"Breakout strategy enabled "
                    f"(lookback: {settings.breakout.lookback}, atr×{settings.breakout.atr_multiplier})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize breakout strategy: {e}")

        if enabled.get("trend_following"):
            try:
                config = {
                    "enabled": True,
                    "asset_class": "equities",
                    "timeframe": "1D",
                    "weight": settings.trend_following.allocation_weight,
                    "fast_sma": settings.trend_following.fast_sma,
                    "slow_sma": settings.trend_following.slow_sma,
                }
                self.strategies["trend_following"] = TrendFollowing(config)
                logger.info(
                    f"Trend following strategy enabled "
                    f"(SMA {settings.trend_following.fast_sma}/{settings.trend_following.slow_sma})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize trend following strategy: {e}")

        if enabled.get("pairs_trading"):
            try:
                config = {
                    "enabled": True,
                    "asset_class": "equities",
                    "timeframe": "1D",
                    "weight": settings.pairs_trading.allocation_weight,
                    "z_entry": settings.pairs_trading.z_entry,
                    "z_exit": settings.pairs_trading.z_exit,
                    "correlation_min": settings.pairs_trading.correlation_min,
                }
                self.strategies["pairs_trading"] = PairsTrading(config)
                logger.info(
                    f"Pairs trading strategy enabled "
                    f"(z_entry: {settings.pairs_trading.z_entry}, corr≥{settings.pairs_trading.correlation_min})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize pairs trading strategy: {e}")

        if enabled.get("volatility_regime"):
            try:
                config = {
                    "enabled": True,
                    "asset_class": "meta",
                    "weight": settings.volatility_regime.allocation_weight,
                    "vix_low": settings.volatility_regime.vix_low,
                    "vix_high": settings.volatility_regime.vix_high,
                }
                self.strategies["volatility_regime"] = VolatilityRegime(config)
                logger.info(
                    f"Volatility regime strategy enabled "
                    f"(VIX bands: {settings.volatility_regime.vix_low}-{settings.volatility_regime.vix_high})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize volatility regime strategy: {e}")

        if enabled.get("ensemble"):
            try:
                config = {
                    "enabled": True,
                    "asset_class": "meta",
                    "weight": settings.ensemble.allocation_weight,
                    "min_confidence": settings.ensemble.min_confidence,
                }
                self.strategies["ensemble"] = EnsembleStrategy(config)
                logger.info("Ensemble strategy enabled (aggregates all signals)")
            except Exception as e:
                logger.error(f"Failed to initialize ensemble strategy: {e}")

        logger.info(f"Strategies initialized: {list(self.strategies.keys())}")

    async def _initialize_risk_manager(self) -> None:
        logger.info("Initializing risk manager...")

        try:
            from risk.manager import RiskManager
            from risk.position_sizer import PositionSizer
            from risk.circuit_breaker import CircuitBreaker

            self.risk_manager = RiskManager(
                initial_equity=settings.trading.initial_capital,
                max_drawdown_pct=settings.trading.max_drawdown_pct,
                max_daily_loss_pct=settings.trading.max_daily_loss_pct,
                max_positions=settings.trading.max_positions,
                max_leverage=settings.trading.max_leverage,
                max_single_position_pct=settings.trading.max_single_position_pct,
                max_loss_per_trade_pct=settings.trading.max_portfolio_risk_percent * 100,
            )

            self.position_sizer = PositionSizer(
                kelly_fraction=settings.trading.kelly_fraction,
                max_position_size=settings.trading.max_position_size_dollars,
                min_position_size=settings.trading.min_position_size_dollars,
            )

            self.circuit_breaker = CircuitBreaker(
                max_daily_loss_pct=settings.trading.max_daily_loss_pct,
                max_drawdown_pct=settings.trading.max_drawdown_pct,
                volatility_threshold=settings.circuit_breaker.volatility_threshold_sigma,
                heartbeat_timeout_sec=settings.circuit_breaker.heartbeat_timeout_seconds,
                cooldown_minutes=settings.circuit_breaker.cooldown_minutes,
                auto_recovery=True,
            )

            logger.info(
                f"Risk limits: "
                f"pos_size={settings.trading.max_position_size_percent}, "
                f"portfolio_risk={settings.trading.max_portfolio_risk_percent}, "
                f"leverage={settings.trading.max_leverage}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize risk manager: {e}", exc_info=True)
            raise

    async def _initialize_data_feed(self) -> None:
        logger.info("Initializing data feed...")

        try:
            from data.feeds import DataFeedManager

            api_key, api_secret, _ = settings.get_alpaca_credentials()

            fred_key = None
            try:
                fred_key = settings.fred.api_key
            except Exception:
                pass

            self.data_feed = DataFeedManager(
                alpaca_api_key=api_key,
                alpaca_secret_key=api_secret,
                fred_api_key=fred_key,
            )
            logger.info("Data feed manager initialized")
        except Exception as e:
            logger.warning(f"Data feed initialization failed: {e} - market data may be unavailable")

    async def _initialize_order_executor(self) -> None:
        logger.info("Initializing order executor...")

        try:
            from core.executor import OrderExecutor
            self.order_executor = OrderExecutor(
                brokers=self.brokers,
                event_bus=event_bus,
            )
            logger.info("Order executor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize order executor: {e}")

    # Keep backward compat - old name pointed at position_manager dict
    async def _initialize_position_manager(self) -> None:
        await self._initialize_data_feed()

    async def _backfill_alpaca_orders(self) -> None:
        """Backfill filled Alpaca orders into DB so historical trades are tracked.

        External orders (made via Alpaca UI or before this system existed)
        get tagged strategy_name='external'. System-placed orders are
        already stored by _process_signal() so we skip those by broker_order_id.
        """
        broker = self.brokers.get("alpaca")
        if not broker or not getattr(broker, "_connected", False):
            logger.debug("Alpaca not connected - skipping backfill")
            return
        if not hasattr(broker, "get_recent_filled_orders"):
            return

        try:
            alpaca_orders = await broker.get_recent_filled_orders(limit=500)
        except Exception as e:
            logger.warning(f"Could not fetch Alpaca orders for backfill: {e}")
            return

        if not alpaca_orders:
            logger.debug("No Alpaca orders to backfill")
            return

        from sqlalchemy import select
        from core.database import DatabaseManager
        from core.models import (
            Order as DBOrder,
            OrderStatus as DBOrderStatus,
            OrderSide as DBOrderSide,
        )

        inserted = 0
        skipped = 0

        SessionLocal = DatabaseManager._async_session_local
        if SessionLocal is None:
            logger.warning("DB session not available for backfill")
            return

        async with SessionLocal() as session:
            for o in alpaca_orders:
                broker_order_id = o.get("broker_order_id") or o.get("id")
                if not broker_order_id:
                    continue

                # Skip if already in DB
                existing = await session.execute(
                    select(DBOrder).where(DBOrder.broker_order_id == str(broker_order_id))
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

                side_str = (o.get("side") or "BUY").upper()
                side_enum = DBOrderSide.BUY if side_str == "BUY" else DBOrderSide.SELL

                filled_at = o.get("filled_at")
                if isinstance(filled_at, str):
                    try:
                        filled_at = datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
                    except Exception:
                        filled_at = None

                db_order = DBOrder(
                    broker_order_id=str(broker_order_id),
                    symbol=o.get("symbol") or "UNKNOWN",
                    side=side_enum,
                    order_type="market",
                    quantity=float(o.get("qty") or 0),
                    filled_quantity=float(o.get("qty") or 0),
                    filled_price=float(o.get("entryPrice") or 0),
                    price=float(o.get("entryPrice") or 0),
                    status=DBOrderStatus.FILLED,
                    strategy_name="external",
                    broker_name="alpaca",
                    trading_mode=settings.mode,
                    filled_at=filled_at,
                    submitted_at=filled_at,
                )
                session.add(db_order)
                inserted += 1

            if inserted > 0:
                try:
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.warning(f"Backfill commit failed: {e}")
                    return

        logger.info(
            f"Alpaca order backfill: {inserted} inserted, {skipped} already present "
            f"(mode={settings.mode})"
        )

    def _start_background_tasks(self):
        """Start periodic background tasks using asyncio."""
        async def _periodic(name, coro_func, interval_seconds):
            """Run a coroutine periodically."""
            logger.info(f"Background task '{name}' started (every {interval_seconds}s)")
            await asyncio.sleep(settings.scheduler.background_task_initial_delay_seconds)  # initial delay
            while self.running:
                try:
                    await coro_func()
                except Exception as e:
                    logger.error(f"Background task '{name}' error: {e}")
                await asyncio.sleep(interval_seconds)

        loop = asyncio.get_event_loop()

        # Data sync
        interval = getattr(settings.scheduler, 'data_sync_interval_seconds', 60)
        if interval > 0:
            task = loop.create_task(_periodic("data_sync", self._sync_market_data, interval))
            self._background_tasks.append(task)

        # Strategy checks
        interval = getattr(settings.scheduler, 'strategy_check_interval_seconds', 300)
        if interval > 0:
            task = loop.create_task(_periodic("strategy_checks", self._run_strategy_checks, interval))
            self._background_tasks.append(task)

        # Risk checks
        interval = getattr(settings.scheduler, 'risk_check_interval_seconds', 60)
        if interval > 0:
            task = loop.create_task(_periodic("risk_checks", self._run_risk_checks, interval))
            self._background_tasks.append(task)

        # Portfolio snapshots
        snapshot_interval = settings.scheduler.portfolio_snapshot_interval_minutes * 60
        task = loop.create_task(_periodic("portfolio_snapshot", self._take_portfolio_snapshot, snapshot_interval))
        self._background_tasks.append(task)

        # Order fill checks
        if self.order_executor:
            task = loop.create_task(_periodic("fill_checks", self._check_order_fills, 30))
            self._background_tasks.append(task)

        # System health
        task = loop.create_task(_periodic("health_check", self._system_health_check, 60))
        self._background_tasks.append(task)

    async def _setup_scheduler(self) -> None:
        logger.info("Setting up scheduler...")

        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler.timezone)

        if settings.scheduler.strategy_check_interval_seconds > 0:
            self.scheduler.add_job(
                self._run_strategy_checks,
                trigger="interval",
                seconds=settings.scheduler.strategy_check_interval_seconds,
                id="strategy_checks",
                replace_existing=True,
            )
            logger.info(
                f"Strategy checks scheduled every {settings.scheduler.strategy_check_interval_seconds}s"
            )

        if settings.scheduler.risk_check_interval_seconds > 0:
            self.scheduler.add_job(
                self._run_risk_checks,
                trigger="interval",
                seconds=settings.scheduler.risk_check_interval_seconds,
                id="risk_checks",
                replace_existing=True,
            )
            logger.info(f"Risk checks scheduled every {settings.scheduler.risk_check_interval_seconds}s")

        if settings.scheduler.data_sync_interval_seconds > 0:
            self.scheduler.add_job(
                self._sync_market_data,
                trigger="interval",
                seconds=settings.scheduler.data_sync_interval_seconds,
                id="data_sync",
                replace_existing=True,
            )
            logger.info(f"Data sync scheduled every {settings.scheduler.data_sync_interval_seconds}s")

        self.scheduler.add_job(
            self._take_portfolio_snapshot,
            trigger="interval",
            minutes=settings.scheduler.portfolio_snapshot_interval_minutes,
            id="portfolio_snapshot",
            replace_existing=True,
        )
        logger.info(f"Portfolio snapshots scheduled every {settings.scheduler.portfolio_snapshot_interval_minutes} minutes")

        # Order fill checks
        if self.order_executor:
            self.scheduler.add_job(
                self._check_order_fills,
                trigger="interval",
                seconds=30,
                id="order_fill_checks",
                replace_existing=True,
            )
            logger.info("Order fill checks scheduled every 30s")

        self.scheduler.add_job(
            self._system_health_check,
            trigger="interval",
            minutes=1,
            id="health_check",
            replace_existing=True,
        )
        logger.info("System health checks scheduled every 1 minute")

    # ── Core loop methods ───────────────────────────────────────────────

    async def _sync_market_data(self) -> None:
        """Fetch OHLCV data for configured symbols."""
        equity_symbols = list(settings.trading.equity_symbols)
        crypto_symbols = list(settings.trading.crypto_symbols)

        if not self.data_feed:
            logger.warning("Data feed not available - skipping market data sync")
            return

        synced = 0
        failed = 0

        # Equities from Alpaca
        for symbol in equity_symbols:
            try:
                df = await self.data_feed.get_ohlcv(
                    symbol=symbol,
                    timeframe=settings.trading.default_timeframe,
                    source="alpaca",
                )
                if df is not None and not df.empty:
                    self._market_data[symbol] = df
                    synced += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.debug(f"Data sync failed for {symbol}: {e}")

        # Crypto from CoinGecko
        for symbol in crypto_symbols:
            try:
                df = await self.data_feed.get_ohlcv(
                    symbol=symbol,
                    timeframe=settings.trading.default_timeframe,
                    source="coingecko",
                )
                if df is not None and not df.empty:
                    self._market_data[symbol] = df
                    synced += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.debug(f"Data sync failed for {symbol}: {e}")

        total = len(equity_symbols) + len(crypto_symbols)
        logger.info(
            f"Market data sync: {synced}/{total} symbols cached ({failed} failed). "
            f"Cache now has {len(self._market_data)} symbols."
        )

        try:
            await event_bus.emit(Event(
                event_type=EventType.DATA_SYNC_COMPLETED,
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow().isoformat(),
                source="engine",
                data={"symbols_synced": synced, "total": len(symbols)},
            ))
        except Exception:
            pass

    async def _run_strategy_checks(self) -> None:
        """Run all enabled strategies and execute approved signals."""
        from strategies.base import BaseStrategy, Direction

        # Circuit breaker gate
        if self.circuit_breaker and not self.circuit_breaker.can_trade():
            logger.warning("Trading halted by circuit breaker")
            return

        # Heartbeat for dead-man's switch
        if self.circuit_breaker:
            self.circuit_breaker.heartbeat()

        total_signals = 0
        checked_strategies = 0

        for name, strategy in self.strategies.items():
            if not isinstance(strategy, BaseStrategy):
                continue
            if not strategy.enabled:
                continue

            checked_strategies += 1
            strategy_signals = 0

            try:
                # Determine symbols for this strategy
                asset_class = strategy.asset_class
                if asset_class == "equities":
                    symbols = list(settings.trading.equity_symbols)
                elif asset_class == "crypto":
                    symbols = list(settings.trading.crypto_symbols)
                else:
                    symbols = list(self._market_data.keys())

                symbols_with_data = 0
                for symbol in symbols:
                    df = self._market_data.get(symbol)
                    if df is None or df.empty:
                        continue
                    symbols_with_data += 1

                    try:
                        signals = strategy.generate_signals(df)
                    except Exception as e:
                        logger.error(f"Signal generation failed for {name}/{symbol}: {e}")
                        continue

                    for sig in signals:
                        strategy_signals += 1
                        total_signals += 1
                        try:
                            await self._process_signal(sig, name, symbol, df)
                        except Exception as e:
                            logger.error(f"Signal processing failed for {name}/{symbol}: {e}")

                logger.info(
                    f"Strategy '{name}': checked {symbols_with_data}/{len(symbols)} symbols, "
                    f"generated {strategy_signals} signals"
                )

            except Exception as e:
                logger.error(f"Strategy {name} check failed: {e}", exc_info=True)
                await event_bus.emit_risk_alert(
                    alert_type="strategy_error",
                    title="Strategy Execution Error",
                    message=str(e),
                    severity="error",
                    strategy_name=name,
                )

        logger.info(
            f"Strategy check complete: {checked_strategies} strategies, "
            f"{total_signals} total signals, "
            f"market_data has {len(self._market_data)} symbols cached"
        )

    async def _process_signal(self, sig, strategy_name: str, symbol: str, df) -> None:
        """Convert a strategy Signal to a risk-checked broker order."""
        from strategies.base import Direction
        from risk.manager import Order as RiskOrder, AssetClass, OrderType as RiskOrderType
        from brokers.base import BaseBroker, OrderSide, OrderType

        # Map direction to side
        if sig.direction == Direction.LONG:
            risk_side = RiskOrderType.BUY
            broker_side = OrderSide.BUY
        elif sig.direction == Direction.SHORT:
            risk_side = RiskOrderType.SHORT
            broker_side = OrderSide.SELL
        elif sig.direction == Direction.EXIT:
            risk_side = RiskOrderType.CLOSE
            broker_side = OrderSide.SELL
        else:
            return  # NEUTRAL, skip

        # Current price from last bar
        current_price = float(df["close"].iloc[-1])

        # Convert dollar position_size to share quantity
        if sig.position_size and sig.position_size > 0 and current_price > 0:
            quantity = sig.position_size / current_price
        else:
            quantity = max(1.0, (self._cash * settings.trading.default_position_size_pct) / current_price) if current_price > 0 else 0

        if quantity <= 0:
            return

        # Determine asset class for risk manager
        asset_class = AssetClass.EQUITY
        if "/" in symbol:
            asset_class = AssetClass.CRYPTO

        # Build risk order
        risk_order = RiskOrder(
            symbol=symbol,
            quantity=quantity,
            price=current_price,
            side=risk_side,
            asset_class=asset_class,
            strategy_id=strategy_name,
        )

        # Risk check
        if self.risk_manager:
            from risk.manager import RiskManager
            if isinstance(self.risk_manager, RiskManager):
                approved, reason = await self.risk_manager.check_order(risk_order)
                if not approved:
                    logger.info(f"Order rejected by risk manager: {symbol} - {reason}")
                    return

        # Emit signal event
        try:
            await event_bus.emit_signal_generated(
                symbol=symbol,
                signal_type=sig.direction.value.lower(),
                strategy_name=strategy_name,
                confidence=sig.strength,
                price=current_price,
                reason=str(sig.metadata),
            )
        except Exception as e:
            logger.debug(f"Failed to emit signal event: {e}")

        # Broadcast signal via websocket
        try:
            from api.websocket import broadcast_signal
            await broadcast_signal(
                strategy=strategy_name,
                symbol=symbol,
                signal_type=sig.direction.value,
                strength=sig.strength,
            )
        except Exception:
            pass

        # Submit to broker
        broker = self.brokers.get("alpaca")
        if broker and isinstance(broker, BaseBroker) and broker.is_connected:
            try:
                broker_order = await broker.submit_order(
                    symbol=symbol,
                    qty=round(quantity, 4),
                    side=broker_side,
                    order_type=OrderType.MARKET,
                )

                logger.info(
                    f"Order submitted: {broker_side.value} {quantity:.4f} {symbol} "
                    f"@ ~${current_price:.2f} (strategy: {strategy_name})"
                )

                # Emit order placed event
                try:
                    await event_bus.emit_order_placed(
                        order_id=str(broker_order.order_id),
                        symbol=symbol,
                        side=broker_side.value,
                        quantity=quantity,
                        price=current_price,
                        strategy_name=strategy_name,
                    )
                except Exception:
                    pass

                # Store order in DB
                try:
                    session = await get_session()
                    async with session:
                        db_order = DBOrder(
                            broker_order_id=str(broker_order.order_id),
                            symbol=symbol,
                            side=DBOrderSide.BUY if broker_side == OrderSide.BUY else DBOrderSide.SELL,
                            order_type="market",
                            quantity=quantity,
                            price=current_price,
                            status=DBOrderStatus.SUBMITTED,
                            strategy_name=strategy_name,
                            broker_name="alpaca",
                            trading_mode=settings.mode,
                            submitted_at=datetime.utcnow(),
                        )
                        session.add(db_order)
                        await session.commit()
                except Exception as e:
                    logger.error(f"Failed to store order in DB: {e}")

                # Track for fill monitoring
                if self.order_executor:
                    await self.order_executor.track_order(
                        order_id=str(broker_order.order_id),
                        broker_name="alpaca",
                        symbol=symbol,
                        side=broker_side.value,
                        quantity=quantity,
                        price=current_price,
                        strategy_name=strategy_name,
                    )

                # Broadcast trade via websocket
                try:
                    from api.websocket import broadcast_new_trade
                    await broadcast_new_trade(
                        trade_id=str(broker_order.order_id),
                        symbol=symbol,
                        side=broker_side.value,
                        quantity=quantity,
                        entry_price=current_price,
                        strategy=strategy_name,
                    )
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Order submission failed for {symbol}: {e}")
        else:
            logger.info(
                f"Paper signal (no broker): {broker_side.value} {quantity:.4f} {symbol} "
                f"@ ~${current_price:.2f} (strategy: {strategy_name})"
            )

    async def _run_risk_checks(self) -> None:
        """Monitor portfolio risk."""
        try:
            from risk.manager import RiskManager

            if not self.risk_manager or not isinstance(self.risk_manager, RiskManager):
                return

            risk = await self.risk_manager.get_portfolio_risk()

            # Update circuit breaker with risk metrics
            if self.circuit_breaker:
                if risk.max_drawdown_breach:
                    await self.circuit_breaker.check_drawdown(risk.max_drawdown_pct)
                if risk.max_daily_loss_breach:
                    daily_loss_pct = abs(risk.today_pnl / risk.total_equity * 100) if risk.total_equity > 0 else 0
                    await self.circuit_breaker.check_daily_loss(daily_loss_pct)

            # Emit alerts for breaches
            if risk.max_drawdown_breach:
                await event_bus.emit_risk_alert(
                    alert_type="max_drawdown",
                    title="Maximum Drawdown Breach",
                    message=f"Drawdown at {risk.max_drawdown_pct:.2f}%",
                    severity="critical",
                )
                try:
                    from api.websocket import broadcast_risk_alert
                    await broadcast_risk_alert(
                        severity="critical",
                        message=f"Max drawdown breach: {risk.max_drawdown_pct:.2f}%",
                        metric="drawdown",
                        value=risk.max_drawdown_pct,
                        threshold=self.risk_manager.max_drawdown_pct,
                    )
                except Exception:
                    pass

            if risk.max_daily_loss_breach:
                await event_bus.emit_risk_alert(
                    alert_type="max_daily_loss",
                    title="Maximum Daily Loss Breach",
                    message=f"Daily P&L: ${risk.today_pnl:.2f}",
                    severity="critical",
                )

            if risk.concentration_breach:
                await event_bus.emit_risk_alert(
                    alert_type="concentration",
                    title="Position Concentration Breach",
                    message="Single position exceeds limit",
                    severity="warning",
                )

        except Exception as e:
            logger.error(f"Risk check error: {e}", exc_info=True)
            await event_bus.emit_risk_alert(
                alert_type="risk_check_error",
                title="Risk Check Error",
                message=str(e),
                severity="critical",
            )

    async def _take_portfolio_snapshot(self) -> None:
        """Snapshot portfolio state."""
        try:
            from brokers.base import BaseBroker

            total_value = self._initial_capital
            cash = self._initial_capital
            positions_value = 0.0
            unrealized_pnl = 0.0
            num_positions = 0

            # Try to get real account data from broker
            broker = self.brokers.get("alpaca")
            if broker and isinstance(broker, BaseBroker) and broker.is_connected:
                try:
                    account = await broker.get_account()
                    total_value = account.balance
                    cash = account.cash
                    positions_value = account.equity - account.cash

                    positions = await broker.get_positions()
                    num_positions = len(positions)
                    unrealized_pnl = sum(p.unrealized_pl for p in positions)
                    self._open_positions = [
                        {
                            "symbol": p.symbol,
                            "quantity": p.quantity,
                            "avg_entry_price": p.avg_entry_price,
                            "current_price": p.current_price,
                            "market_value": p.market_value,
                            "unrealized_pl": p.unrealized_pl,
                            "unrealized_pl_pct": p.unrealized_pl_pct,
                        }
                        for p in positions
                    ]
                except Exception as e:
                    logger.warning(f"Could not fetch broker account data: {e}")

            # Update engine state
            self._portfolio_value = total_value
            self._cash = cash
            self._positions_value = positions_value
            self._total_pnl = total_value - self._initial_capital
            return_pct = ((total_value - self._initial_capital) / self._initial_capital * 100) if self._initial_capital > 0 else 0.0

            # Update risk manager equity
            if self.risk_manager:
                try:
                    from risk.manager import RiskManager
                    if isinstance(self.risk_manager, RiskManager):
                        self.risk_manager.current_equity = total_value
                except Exception:
                    pass

            # Store snapshot in DB
            try:
                session = await get_session()
                async with session:
                    snapshot = PortfolioSnapshot(
                        timestamp=datetime.utcnow(),
                        total_value=total_value,
                        cash=cash,
                        positions_value=positions_value,
                        unrealized_gain_loss=unrealized_pnl,
                        total_profit_loss=self._total_pnl,
                        return_percent=return_pct,
                        num_open_positions=num_positions,
                    )
                    session.add(snapshot)
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to store portfolio snapshot: {e}")

            # Broadcast via websocket
            try:
                from api.websocket import broadcast_portfolio_update
                await broadcast_portfolio_update(
                    portfolio_value=total_value,
                    cash=cash,
                    invested=positions_value,
                    daily_pnl=self._daily_pnl,
                    total_pnl=self._total_pnl,
                    daily_pnl_percentage=(self._daily_pnl / total_value * 100) if total_value > 0 else 0,
                )
            except Exception:
                pass

            # Emit portfolio update event
            try:
                await event_bus.emit_portfolio_update(
                    total_value=total_value,
                    cash=cash,
                    positions_value=positions_value,
                    unrealized_gain_loss=unrealized_pnl,
                    return_percent=return_pct,
                )
            except Exception:
                pass

            logger.debug(f"Portfolio snapshot: ${total_value:,.2f} (PnL: ${self._total_pnl:,.2f})")

        except Exception as e:
            logger.error(f"Snapshot error: {e}", exc_info=True)

    async def _check_order_fills(self) -> None:
        """Check pending orders for fills."""
        if self.order_executor:
            try:
                await self.order_executor.check_fills()
            except Exception as e:
                logger.error(f"Order fill check error: {e}")

    # ── Event handlers ──────────────────────────────────────────────────

    async def _handle_signal_event(self, event: Event) -> None:
        logger.debug(f"Signal event received: {event.data}")

    async def _handle_fill_event(self, event: Event) -> None:
        logger.info(f"Order filled: {event.data}")

    async def _handle_risk_alert(self, event: Event) -> None:
        severity = event.data.get("severity", "warning")
        logger.warning(f"Risk alert [{severity}]: {event.data.get('message', '')}")
        if severity == "critical" and self.circuit_breaker:
            await self.circuit_breaker.check_system_error(
                event.data.get("message", "Unknown risk alert"),
                critical=False,
            )

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            await self.initialize()
            self.running = True

            if self.scheduler:
                self.scheduler.start()
                logger.info("Scheduler started")

            logger.info("Starting event bus listener...")
            event_bus_task = asyncio.create_task(event_bus.start_listening())

            logger.info("=" * 80)
            logger.info(f"{settings.app_name} is running!")
            logger.info(f"Uptime: {self._get_uptime()}")
            logger.info("=" * 80)

            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)
            await self.shutdown()

    async def shutdown(self) -> None:
        logger.info("=" * 80)
        logger.info("Shutting down trading engine...")
        logger.info("=" * 80)

        self.running = False

        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("Scheduler stopped")

            # Disconnect brokers
            from brokers.base import BaseBroker
            for name, broker in self.brokers.items():
                if isinstance(broker, BaseBroker) and broker.is_connected:
                    try:
                        await broker.disconnect()
                        logger.info(f"Broker {name} disconnected")
                    except Exception as e:
                        logger.error(f"Error disconnecting broker {name}: {e}")

            await event_bus.stop_listening()
            await event_bus.disconnect()
            logger.info("Event bus disconnected")

            await DatabaseManager.close()
            logger.info("Database closed")

            logger.info(f"Total uptime: {self._get_uptime()}")
            logger.info("Shutdown complete")

        except Exception as e:
            logger.error(f"Shutdown error: {e}", exc_info=True)

    async def _system_health_check(self) -> None:
        try:
            db_healthy = await DatabaseManager.health_check()
            status = "healthy" if db_healthy else "degraded"

            # Count active positions and orders
            num_positions = len(self._open_positions)
            num_orders = 0
            if self.order_executor:
                num_orders = len(self.order_executor.pending_orders)

            await event_bus.emit_system_health(
                status=status,
                uptime_seconds=self._get_uptime_seconds(),
                active_positions=num_positions,
                active_orders=num_orders,
                memory_usage_percent=0.0,
            )
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)

    def _get_uptime(self) -> str:
        if not self.start_time:
            return "N/A"
        delta = datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def _get_uptime_seconds(self) -> float:
        if not self.start_time:
            return 0.0
        return (datetime.utcnow() - self.start_time).total_seconds()

    def handle_signal(self, signum: int, frame: any) -> None:
        logger.info(f"Received signal {signum}")
        asyncio.create_task(self.shutdown())


async def run_engine() -> None:
    engine = TradingEngine()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, engine.handle_signal)

    try:
        await engine.start()
    except KeyboardInterrupt:
        await engine.shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        await engine.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_engine())
