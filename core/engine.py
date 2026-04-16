"""
Main trading engine orchestrating all system components.
Handles broker initialization, strategy execution, and graceful shutdown.
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.settings import settings
from core.database import DatabaseManager, init_db
from core.events import event_bus, EventType
from core.models import SystemLog


class TradingEngine:
    """Main trading engine coordinating all components."""

    def __init__(self) -> None:
        """Initialize the trading engine."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.running = False
        self.start_time: Optional[datetime] = None
        self.strategies: Dict[str, any] = {}
        self.brokers: Dict[str, any] = {}
        self.risk_manager: Optional[any] = None
        self.position_manager: Optional[any] = None

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

    @property
    def portfolio_value(self) -> float:
        if self.position_manager:
            return self.position_manager.get('initial_capital', 100000.0)
        return 100000.0

    @property
    def cash(self) -> float:
        return self.portfolio_value

    @property
    def daily_pnl(self) -> float:
        return 0.0

    @property
    def total_pnl(self) -> float:
        return 0.0

    @property
    def total_pnl_percentage(self) -> float:
        return 0.0

    @property
    def initial_capital(self) -> float:
        if self.position_manager:
            return self.position_manager.get('initial_capital', 100000.0)
        return 100000.0

    @property
    def win_rate(self) -> float:
        return 0.0

    @property
    def sharpe_ratio(self) -> float:
        return 0.0

    @property
    def annual_return(self) -> float:
        return 0.0

    @property
    def max_drawdown(self) -> float:
        return 0.0

    @property
    def profit_factor(self) -> float:
        return 0.0

    @property
    def avg_trade_duration_hours(self) -> float:
        return 0.0

    @property
    def open_positions(self) -> list:
        return []

    @property
    def trading_mode(self) -> str:
        return settings.mode

    async def initialize(self) -> None:
        """Initialize all system components."""
        logger.info("=" * 80)
        logger.info(f"Initializing {settings.app_name} v1.0.0")
        logger.info(f"Mode: {settings.mode.upper()}")
        logger.info(f"Environment: {settings.environment}")
        logger.info("=" * 80)

        try:
            # Initialize database
            logger.info("Setting up database...")
            await DatabaseManager.init()
            await init_db()
            logger.info("Database initialized successfully")

            # Connect event bus
            logger.info("Connecting event bus...")
            await event_bus.connect()
            logger.info("Event bus connected")

            # Initialize brokers
            await self._initialize_brokers()

            # Initialize strategies
            await self._initialize_strategies()

            # Initialize risk manager
            await self._initialize_risk_manager()

            # Initialize position manager
            await self._initialize_position_manager()

            # Setup scheduler
            await self._setup_scheduler()

            logger.info("Trading engine initialization complete")
            self.start_time = datetime.utcnow()

        except Exception as e:
            logger.error(f"Initialization error: {e}", exc_info=True)
            raise

    async def _initialize_brokers(self) -> None:
        """Initialize broker connections."""
        logger.info("Initializing brokers...")

        try:
            # Alpaca broker
            api_key, api_secret, base_url = settings.get_alpaca_credentials()
            logger.info(f"Alpaca broker initialized (Mode: {settings.mode})")
            self.brokers["alpaca"] = {
                "api_key": api_key,
                "api_secret": api_secret,
                "base_url": base_url,
                "mode": settings.mode,
            }

            # IBKR broker (if configured)
            if settings.ibkr.account_id:
                logger.info("Interactive Brokers configured")
                self.brokers["ibkr"] = {
                    "account_id": settings.ibkr.account_id,
                    "host": settings.ibkr.host,
                    "port": settings.ibkr.port,
                    "client_id": settings.ibkr.client_id,
                }

            # Polymarket (if configured)
            if settings.polymarket.api_key:
                logger.info("Polymarket configured")
                self.brokers["polymarket"] = {
                    "api_key": settings.polymarket.api_key,
                    "base_url": settings.polymarket.base_url,
                }

            logger.info(f"Brokers initialized: {list(self.brokers.keys())}")

        except Exception as e:
            logger.error(f"Broker initialization error: {e}", exc_info=True)
            raise

    async def _initialize_strategies(self) -> None:
        """Initialize trading strategies."""
        logger.info("Initializing strategies...")

        enabled_strategies = settings.get_enabled_strategies()

        if enabled_strategies["momentum"]:
            logger.info(
                f"Momentum strategy enabled (lookback: {settings.momentum.lookback}, "
                f"threshold: {settings.momentum.threshold})"
            )
            self.strategies["momentum"] = {
                "enabled": True,
                "lookback": settings.momentum.lookback,
                "threshold": settings.momentum.threshold,
                "allocation_weight": settings.momentum.allocation_weight,
            }

        if enabled_strategies["mean_reversion"]:
            logger.info(
                f"Mean reversion strategy enabled (z_score: {settings.mean_reversion.z_score}, "
                f"window: {settings.mean_reversion.window})"
            )
            self.strategies["mean_reversion"] = {
                "enabled": True,
                "z_score": settings.mean_reversion.z_score,
                "window": settings.mean_reversion.window,
                "allocation_weight": settings.mean_reversion.allocation_weight,
            }

        if enabled_strategies["crypto_momentum"]:
            logger.info(f"Crypto momentum strategy enabled (lookback: {settings.crypto_momentum.lookback})")
            self.strategies["crypto_momentum"] = {
                "enabled": True,
                "lookback": settings.crypto_momentum.lookback,
                "allocation_weight": settings.crypto_momentum.allocation_weight,
            }

        if enabled_strategies["options_wheel"]:
            logger.info(f"Options wheel strategy enabled (target yield: {settings.options_wheel.target_yield_percent})")
            self.strategies["options_wheel"] = {
                "enabled": True,
                "target_yield": settings.options_wheel.target_yield_percent,
                "allocation_weight": settings.options_wheel.allocation_weight,
            }

        if enabled_strategies["polymarket"]:
            logger.info(f"Polymarket strategy enabled (confidence: {settings.polymarket_strategy.confidence_threshold})")
            self.strategies["polymarket"] = {
                "enabled": True,
                "confidence_threshold": settings.polymarket_strategy.confidence_threshold,
                "allocation_weight": settings.polymarket_strategy.allocation_weight,
            }

        logger.info(f"Strategies initialized: {list(self.strategies.keys())}")

    async def _initialize_risk_manager(self) -> None:
        """Initialize risk management system."""
        logger.info("Initializing risk manager...")

        self.risk_manager = {
            "max_position_size": settings.trading.max_position_size_percent,
            "max_portfolio_risk": settings.trading.max_portfolio_risk_percent,
            "max_leverage": settings.trading.max_leverage,
            "min_cash_buffer": settings.trading.min_cash_buffer_percent,
            "max_slippage": settings.trading.max_slippage_percent,
        }

        logger.info(
            f"Risk limits: "
            f"pos_size={self.risk_manager['max_position_size']}, "
            f"portfolio_risk={self.risk_manager['max_portfolio_risk']}, "
            f"leverage={self.risk_manager['max_leverage']}"
        )

    async def _initialize_position_manager(self) -> None:
        """Initialize position management system."""
        logger.info("Initializing position manager...")

        self.position_manager = {
            "initial_capital": settings.trading.initial_capital,
            "commission_per_trade": settings.trading.commission_per_trade,
            "slippage_percent": settings.trading.slippage_percent,
        }

        logger.info(f"Initial capital: ${self.position_manager['initial_capital']:.2f}")

    async def _setup_scheduler(self) -> None:
        """Setup APScheduler for periodic tasks."""
        logger.info("Setting up scheduler...")

        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler.timezone)

        # Strategy checks
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

        # Risk checks
        if settings.scheduler.risk_check_interval_seconds > 0:
            self.scheduler.add_job(
                self._run_risk_checks,
                trigger="interval",
                seconds=settings.scheduler.risk_check_interval_seconds,
                id="risk_checks",
                replace_existing=True,
            )
            logger.info(f"Risk checks scheduled every {settings.scheduler.risk_check_interval_seconds}s")

        # Data sync
        if settings.scheduler.data_sync_interval_seconds > 0:
            self.scheduler.add_job(
                self._sync_market_data,
                trigger="interval",
                seconds=settings.scheduler.data_sync_interval_seconds,
                id="data_sync",
                replace_existing=True,
            )
            logger.info(f"Data sync scheduled every {settings.scheduler.data_sync_interval_seconds}s")

        # Portfolio snapshot
        self.scheduler.add_job(
            self._take_portfolio_snapshot,
            trigger="interval",
            minutes=5,
            id="portfolio_snapshot",
            replace_existing=True,
        )
        logger.info("Portfolio snapshots scheduled every 5 minutes")

        # System health check
        self.scheduler.add_job(
            self._system_health_check,
            trigger="interval",
            minutes=1,
            id="health_check",
            replace_existing=True,
        )
        logger.info("System health checks scheduled every 1 minute")

    async def start(self) -> None:
        """Start the trading engine."""
        try:
            await self.initialize()
            self.running = True

            # Start scheduler
            if self.scheduler:
                self.scheduler.start()
                logger.info("Scheduler started")

            # Start event bus listener
            logger.info("Starting event bus listener...")
            event_bus_task = asyncio.create_task(event_bus.start_listening())

            logger.info("=" * 80)
            logger.info(f"{settings.app_name} is running!")
            logger.info(f"Uptime: {self._get_uptime()}")
            logger.info("=" * 80)

            # Keep engine running
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Engine error: {e}", exc_info=True)
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown the trading engine."""
        logger.info("=" * 80)
        logger.info("Shutting down trading engine...")
        logger.info("=" * 80)

        self.running = False

        try:
            # Stop scheduler
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("Scheduler stopped")

            # Stop event bus
            await event_bus.stop_listening()
            await event_bus.disconnect()
            logger.info("Event bus disconnected")

            # Close database
            await DatabaseManager.close()
            logger.info("Database closed")

            logger.info(f"Total uptime: {self._get_uptime()}")
            logger.info("Shutdown complete")

        except Exception as e:
            logger.error(f"Shutdown error: {e}", exc_info=True)

    async def _run_strategy_checks(self) -> None:
        """Run all enabled strategies."""
        try:
            logger.debug("Running strategy checks...")
            for strategy_name in self.strategies:
                if self.strategies[strategy_name]["enabled"]:
                    logger.debug(f"Checking strategy: {strategy_name}")
                    # Strategy execution would happen here
        except Exception as e:
            logger.error(f"Strategy check error: {e}", exc_info=True)
            await event_bus.emit_risk_alert(
                alert_type="strategy_error",
                title="Strategy Execution Error",
                message=str(e),
                severity="error",
            )

    async def _run_risk_checks(self) -> None:
        """Run risk management checks."""
        try:
            logger.debug("Running risk checks...")
            # Risk check logic would happen here
        except Exception as e:
            logger.error(f"Risk check error: {e}", exc_info=True)
            await event_bus.emit_risk_alert(
                alert_type="risk_check_error",
                title="Risk Check Error",
                message=str(e),
                severity="critical",
            )

    async def _sync_market_data(self) -> None:
        """Sync market data from brokers."""
        try:
            logger.debug("Syncing market data...")
            # Data sync logic would happen here
        except Exception as e:
            logger.error(f"Data sync error: {e}", exc_info=True)

    async def _take_portfolio_snapshot(self) -> None:
        """Take a snapshot of the current portfolio."""
        try:
            logger.debug("Taking portfolio snapshot...")
            # Portfolio snapshot logic would happen here
        except Exception as e:
            logger.error(f"Portfolio snapshot error: {e}", exc_info=True)

    async def _system_health_check(self) -> None:
        """Check system health."""
        try:
            db_healthy = await DatabaseManager.health_check()
            status = "healthy" if db_healthy else "degraded"

            await event_bus.emit_system_health(
                status=status,
                uptime_seconds=self._get_uptime_seconds(),
                active_positions=0,
                active_orders=0,
                memory_usage_percent=0.0,
            )
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)

    def _get_uptime(self) -> str:
        """Get formatted uptime."""
        if not self.start_time:
            return "N/A"

        delta = datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def _get_uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        if not self.start_time:
            return 0.0
        return (datetime.utcnow() - self.start_time).total_seconds()

    def handle_signal(self, signum: int, frame: any) -> None:
        """Handle system signals."""
        logger.info(f"Received signal {signum}")
        asyncio.create_task(self.shutdown())


async def run_engine() -> None:
    """Run the trading engine with signal handling."""
    engine = TradingEngine()

    # Register signal handlers
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
