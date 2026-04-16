"""
System management endpoints.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_engine
from core.engine import TradingEngine

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class ComponentHealth(BaseModel):
    name: str
    status: str = Field(..., description="healthy, degraded, unhealthy")
    message: Optional[str] = None
    last_check: datetime
    response_time_ms: Optional[float] = None


class SystemHealthResponse(BaseModel):
    overall_status: str = Field(..., description="healthy, degraded, unhealthy")
    timestamp: datetime
    database: ComponentHealth
    broker_alpaca: ComponentHealth
    broker_ibkr: ComponentHealth
    broker_polymarket: ComponentHealth
    market_data_feeds: ComponentHealth
    scheduler: ComponentHealth
    engine: ComponentHealth


class LogEntry(BaseModel):
    timestamp: datetime
    level: str = Field(..., description="DEBUG, INFO, WARNING, ERROR, CRITICAL")
    logger: str
    message: str


class LogsResponse(BaseModel):
    logs: list[LogEntry]
    total: int
    level_counts: dict[str, int]


class ConfigResponse(BaseModel):
    environment: str
    debug: bool
    trading_mode: str = Field(..., description="paper or live")
    api_version: str
    features: dict[str, bool]
    brokers_enabled: list[str]
    strategies_enabled: list[str]
    database: str
    timestamp: datetime


class ModeSwitchRequest(BaseModel):
    mode: str = Field(..., description="paper or live")
    reason: Optional[str] = None


class ModeSwitchResponse(BaseModel):
    previous_mode: str
    new_mode: str
    timestamp: datetime
    message: str


class ScheduledJob(BaseModel):
    name: str
    task: str
    schedule: str
    next_run: datetime
    last_run: Optional[datetime]
    status: str = Field(..., description="running, idle, failed")
    run_count: int


class SchedulerResponse(BaseModel):
    status: str = Field(..., description="running, paused, stopped")
    jobs: list[ScheduledJob]
    total_jobs: int
    active_jobs: int
    timestamp: datetime


@router.get("/system/health", response_model=SystemHealthResponse)
async def get_system_health(
    engine: TradingEngine = Depends(get_engine),
):
    """
    Check system health: database, brokers, feeds, scheduler.
    """
    try:
        from datetime import datetime as dt

        now = dt.utcnow()
        _default = lambda name: ComponentHealth(name=name, status="unknown", last_check=now)

        try:
            db_status = await _check_database()
        except Exception:
            db_status = _default("Database")

        try:
            alpaca_status = await _check_alpaca_broker(engine)
        except Exception:
            alpaca_status = _default("Alpaca")

        ibkr_status = ComponentHealth(
            name="IBKR", status="degraded", message="Not configured", last_check=now
        )
        polymarket_status = ComponentHealth(
            name="Polymarket", status="degraded", message="Not configured", last_check=now
        )

        try:
            feeds_status = await engine.check_feeds_health()
        except Exception:
            feeds_status = _default("Market Data Feeds")

        try:
            scheduler_status = await engine.check_scheduler_health()
        except Exception:
            scheduler_status = _default("Scheduler")

        try:
            engine_status = await engine.check_engine_health()
        except Exception:
            engine_status = _default("Engine")

        all_statuses = [
            db_status.status,
            alpaca_status.status,
            ibkr_status.status,
            polymarket_status.status,
            feeds_status.status,
            scheduler_status.status,
            engine_status.status,
        ]

        if "unhealthy" in all_statuses:
            overall = "unhealthy"
        elif "degraded" in all_statuses or "unknown" in all_statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        return SystemHealthResponse(
            overall_status=overall,
            timestamp=now,
            database=db_status,
            broker_alpaca=alpaca_status,
            broker_ibkr=ibkr_status,
            broker_polymarket=polymarket_status,
            market_data_feeds=feeds_status,
            scheduler=scheduler_status,
            engine=engine_status,
        )

    except Exception as e:
        logger.error(f"Error checking system health: {e}", exc_info=True)
        now = datetime.utcnow()
        _default = lambda name: ComponentHealth(name=name, status="unknown", last_check=now)
        return SystemHealthResponse(
            overall_status="degraded",
            timestamp=now,
            database=_default("Database"),
            broker_alpaca=_default("Alpaca"),
            broker_ibkr=_default("IBKR"),
            broker_polymarket=_default("Polymarket"),
            market_data_feeds=_default("Market Data Feeds"),
            scheduler=_default("Scheduler"),
            engine=_default("Engine"),
        )


@router.get("/system/logs", response_model=LogsResponse)
async def get_system_logs(
    level: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get recent system logs with optional level filtering."""
    try:
        # TODO: Integrate with logging system
        # This would fetch from a centralized logging store
        logs = []
        level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

        return LogsResponse(
            logs=logs,
            total=len(logs),
            level_counts=level_counts,
        )

    except Exception as e:
        logger.error(f"Error fetching logs: {e}", exc_info=True)
        return LogsResponse(
            logs=[], total=0,
            level_counts={"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0},
        )


@router.get("/system/config", response_model=ConfigResponse)
async def get_system_config():
    """Get current configuration (sanitized, no secrets)."""
    try:
        from api.deps import get_settings as _get_settings
        settings = await _get_settings()

        return ConfigResponse(
            environment=settings.get("environment", "production"),
            debug=settings.get("debug", False),
            trading_mode=settings.get("trading_mode", "paper"),
            api_version="1.0.0",
            features={
                "multi_asset": True,
                "genetic_algorithm": True,
                "reinforcement_learning": True,
                "risk_management": True,
            },
            brokers_enabled=settings.get("brokers_enabled", ["alpaca", "ibkr", "polymarket"]),
            strategies_enabled=settings.get("strategies_enabled", []),
            database=settings.get("database", "postgresql"),
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error fetching config: {e}", exc_info=True)
        return ConfigResponse(
            environment="production", debug=False, trading_mode="paper",
            api_version="1.0.0", features={}, brokers_enabled=[],
            strategies_enabled=[], database="postgresql",
            timestamp=datetime.utcnow(),
        )


@router.post("/system/mode", response_model=ModeSwitchResponse)
async def switch_trading_mode(
    mode_switch: ModeSwitchRequest,
    engine: TradingEngine = Depends(get_engine),
):
    """Switch between paper and live trading mode."""
    try:
        if mode_switch.mode.lower() not in ("paper", "live"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Mode must be 'paper' or 'live'",
            )

        previous_mode = engine.trading_mode
        await engine.switch_trading_mode(mode_switch.mode.lower())

        return ModeSwitchResponse(
            previous_mode=previous_mode,
            new_mode=mode_switch.mode.lower(),
            timestamp=datetime.utcnow(),
            message=f"Trading mode switched from {previous_mode} to {mode_switch.mode.lower()}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching mode: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch trading mode",
        )


@router.get("/system/scheduler", response_model=SchedulerResponse)
async def get_scheduler_status(
    engine: TradingEngine = Depends(get_engine),
):
    """Get scheduled jobs status."""
    try:
        scheduler_status = await engine.get_scheduler_status()

        return SchedulerResponse(
            status=scheduler_status.get("status", "running"),
            jobs=[
                ScheduledJob(
                    name=job.get("name"),
                    task=job.get("task"),
                    schedule=job.get("schedule"),
                    next_run=job.get("next_run", datetime.utcnow()),
                    last_run=job.get("last_run"),
                    status=job.get("status", "idle"),
                    run_count=job.get("run_count", 0),
                )
                for job in scheduler_status.get("jobs", [])
            ],
            total_jobs=scheduler_status.get("total_jobs", 0),
            active_jobs=scheduler_status.get("active_jobs", 0),
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error fetching scheduler status: {e}", exc_info=True)
        return SchedulerResponse(
            status="unknown", jobs=[], total_jobs=0,
            active_jobs=0, timestamp=datetime.utcnow(),
        )


@router.post("/system/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_trading_engine(
    reason: Optional[str] = Query(None),
    engine: TradingEngine = Depends(get_engine),
):
    """
    Restart trading engine (async operation).
    """
    try:
        # Spawn restart as background task
        import asyncio

        asyncio.create_task(_restart_engine(engine, reason))

        return {
            "message": "Engine restart initiated",
            "status": "in_progress",
            "timestamp": datetime.utcnow(),
        }

    except Exception as e:
        logger.error(f"Error restarting engine: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restart engine",
        )


# Helper functions
async def _check_database() -> ComponentHealth:
    """Check database connectivity."""
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text
        import time

        start = time.time()
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        elapsed = (time.time() - start) * 1000

        return ComponentHealth(
            name="Database",
            status="healthy",
            last_check=datetime.utcnow(),
            response_time_ms=elapsed,
        )

    except Exception as e:
        logger.warning(f"Database check failed: {e}")
        return ComponentHealth(
            name="Database",
            status="unhealthy",
            message=str(e),
            last_check=datetime.utcnow(),
        )


async def _restart_engine(engine: TradingEngine, reason: Optional[str]):
    """Restart the trading engine."""
    try:
        logger.info(f"Restarting engine... Reason: {reason}")
        await engine.shutdown()
        await engine.initialize()
        logger.info("Engine restart complete")
    except Exception as e:
        logger.error(f"Engine restart failed: {e}", exc_info=True)


async def _check_alpaca_broker(engine) -> ComponentHealth:
    """Check Alpaca broker health by calling get_account()."""
    try:
        broker = engine.brokers.get("alpaca") if engine else None
        if not broker:
            return ComponentHealth(
                name="Alpaca", status="unhealthy",
                message="Not initialized", last_check=datetime.utcnow(),
            )
        if not broker._connected:
            return ComponentHealth(
                name="Alpaca", status="unhealthy",
                message="Disconnected", last_check=datetime.utcnow(),
            )

        import time
        start = time.time()
        account = await broker.get_account()
        elapsed = (time.time() - start) * 1000
        return ComponentHealth(
            name="Alpaca",
            status="healthy",
            message=f"Account: {getattr(account, 'account_id', 'unknown')}",
            last_check=datetime.utcnow(),
            response_time_ms=elapsed,
        )
    except Exception as e:
        return ComponentHealth(
            name="Alpaca", status="unhealthy",
            message=str(e)[:100], last_check=datetime.utcnow(),
        )
