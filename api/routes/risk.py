"""
Risk monitoring endpoints.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_engine
from config.settings import settings
from core.engine import TradingEngine

logger = logging.getLogger(__name__)

router = APIRouter()


# Response models
class RiskMetric(BaseModel):
    name: str
    value: float
    unit: str
    status: str = Field(..., description="green, yellow, red")
    threshold: Optional[float] = None
    alert: Optional[str] = None


class RiskOverview(BaseModel):
    var_95: float = Field(..., description="Value at Risk 95%")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    total_exposure: float
    leverage: float
    risk_metrics: list[RiskMetric]
    portfolio_heat: float = Field(..., description="Overall portfolio risk heat (0-100)")
    timestamp: datetime


class RiskLimit(BaseModel):
    name: str
    current_value: float
    limit_value: float
    limit_type: str
    usage_percentage: float
    status: str = Field(..., description="ok, warning, violated")
    description: Optional[str] = None


class RiskLimitsResponse(BaseModel):
    limits: list[RiskLimit]
    timestamp: datetime


class UpdateRiskLimitRequest(BaseModel):
    name: str
    limit_value: float = Field(..., gt=0)
    description: Optional[str] = None


class CircuitBreakerStatus(BaseModel):
    active: bool
    triggered_at: Optional[datetime]
    reason: Optional[str]
    triggered_by_metric: Optional[str]
    reset_in_seconds: Optional[int]
    status: str = Field(..., description="active, inactive, cooldown")


class RiskAlert(BaseModel):
    id: str
    severity: str = Field(..., description="low, medium, high, critical")
    message: str
    metric: str
    value: float
    threshold: float
    timestamp: datetime
    acknowledged: bool


class RiskAlertListResponse(BaseModel):
    alerts: list[RiskAlert]
    total: int
    critical: int
    high: int
    medium: int


@router.get("/risk/overview")
async def get_risk_overview(
    engine: TradingEngine = Depends(get_engine),
):
    """Get real risk data from Alpaca broker + RiskManager."""
    try:
        broker = engine.brokers.get("alpaca") if engine.brokers else None
        portfolio_value = engine.portfolio_value or settings.trading.initial_capital

        # Real exposure + drawdown from Alpaca
        exposure_pct = 0.0
        drawdown_pct = 0.0
        daily_loss_dollars = 0.0
        leverage_mult = 0.0
        if broker and getattr(broker, '_connected', False):
            try:
                positions = await broker.get_positions()
                total_abs = sum(abs(float(p.market_value or 0)) for p in positions)
                exposure_pct = (total_abs / portfolio_value * 100) if portfolio_value else 0.0
                leverage_mult = exposure_pct / 100.0
            except Exception as e:
                logger.debug(f"Failed to get positions for exposure: {e}")
            try:
                account = await broker.get_account()
                # Use broker raw client for account fields
                raw = getattr(broker, 'client', None)
                if raw:
                    try:
                        ra = raw.get_account()
                        current_equity = float(getattr(ra, 'equity', portfolio_value))
                        last_equity = float(getattr(ra, 'last_equity', current_equity))
                        daily_loss_dollars = last_equity - current_equity  # positive = loss
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Failed to get account for daily loss: {e}")

        # Drawdown from RiskManager if available
        risk_mgr = engine.risk_manager
        if risk_mgr and hasattr(risk_mgr, 'peak_equity'):
            peak = float(getattr(risk_mgr, 'peak_equity', portfolio_value) or portfolio_value)
            current = float(getattr(risk_mgr, 'current_equity', portfolio_value) or portfolio_value)
            if peak > 0 and current < peak:
                drawdown_pct = (peak - current) / peak * 100

        # Circuit breaker status
        cb = getattr(engine, 'circuit_breaker', None)
        cb_status = "armed"
        if cb is not None:
            try:
                cb_status = "armed" if cb.can_trade() else "halted"
            except Exception:
                pass

        # Limits in both percent and dollars
        max_daily_loss_pct = float(settings.trading.max_daily_loss_pct)
        max_daily_loss_dollars = portfolio_value * (max_daily_loss_pct / 100)
        max_drawdown_pct = float(settings.trading.max_drawdown_pct)
        max_exposure_pct = float(settings.trading.max_leverage * 100)

        return {
            "var_95": 0.0,
            "drawdown": drawdown_pct,
            "max_drawdown": max_drawdown_pct,
            "current_drawdown": drawdown_pct,
            "total_exposure": exposure_pct,
            "exposure": exposure_pct,
            "max_exposure": max_exposure_pct,
            "leverage": leverage_mult,
            "max_leverage": float(settings.trading.max_leverage),
            "daily_loss": max(0.0, daily_loss_dollars),  # dollars lost today
            "daily_loss_pct": (max(0.0, daily_loss_dollars) / portfolio_value * 100) if portfolio_value else 0.0,
            "max_daily_loss": max_daily_loss_pct,
            "max_daily_loss_dollars": max_daily_loss_dollars,
            "portfolio_value": portfolio_value,
            "circuit_breaker_status": cb_status,
            "risk_metrics": [],
            "portfolio_heat": exposure_pct,
            "alerts": [],
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Risk overview error: {e}", exc_info=True)
        return {
            "var_95": 0.0, "drawdown": 0.0, "max_drawdown": settings.trading.max_drawdown_pct,
            "current_drawdown": 0.0, "total_exposure": 0.0, "exposure": 0.0,
            "max_exposure": settings.trading.max_leverage * 100,
            "leverage": 0.0, "max_leverage": settings.trading.max_leverage,
            "daily_loss": 0.0, "daily_loss_pct": 0.0,
            "max_daily_loss": settings.trading.max_daily_loss_pct,
            "max_daily_loss_dollars": settings.trading.initial_capital * (settings.trading.max_daily_loss_pct / 100),
            "portfolio_value": settings.trading.initial_capital,
            "circuit_breaker_status": "armed",
            "risk_metrics": [], "portfolio_heat": 0.0, "alerts": [],
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/risk/limits", response_model=RiskLimitsResponse)
async def get_risk_limits(
    engine: TradingEngine = Depends(get_engine),
):
    """Get current risk limits and usage."""
    try:
        limits = [
            RiskLimit(
                name="Max Daily Loss",
                current_value=abs(engine.daily_pnl),
                limit_value=engine.max_daily_loss,
                limit_type="daily",
                usage_percentage=(abs(engine.daily_pnl) / engine.max_daily_loss * 100) if engine.max_daily_loss > 0 else 0,
                status="violated" if engine.daily_pnl < -engine.max_daily_loss else "ok",
                description="Maximum loss allowed per day",
            ),
            RiskLimit(
                name="Max Position Size",
                current_value=engine.max_position_size,
                limit_value=engine.max_position_size,
                limit_type="position",
                usage_percentage=100.0,
                status="ok",
                description="Maximum size for individual positions",
            ),
            RiskLimit(
                name="Max Leverage",
                current_value=engine.leverage,
                limit_value=settings.trading.max_leverage,
                limit_type="leverage",
                usage_percentage=(engine.leverage / settings.trading.max_leverage * 100) if settings.trading.max_leverage > 0 else 0,
                status="warning" if engine.leverage > (settings.trading.max_leverage * 0.83) else "ok",
                description="Maximum portfolio leverage",
            ),
            RiskLimit(
                name="Max Drawdown",
                current_value=abs(engine.max_drawdown),
                limit_value=settings.trading.max_drawdown_pct,
                limit_type="drawdown",
                usage_percentage=(abs(engine.max_drawdown) / settings.trading.max_drawdown_pct * 100) if settings.trading.max_drawdown_pct > 0 else 0,
                status="violated" if abs(engine.max_drawdown) > settings.trading.max_drawdown_pct else "ok",
                description="Maximum drawdown from peak",
            ),
        ]

        return RiskLimitsResponse(
            limits=limits,
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error fetching risk limits: {e}", exc_info=True)
        return {"limits": [], "timestamp": datetime.utcnow().isoformat()}


@router.put("/risk/limits", status_code=status.HTTP_200_OK)
async def update_risk_limits(
    limit_update: UpdateRiskLimitRequest,
    engine: TradingEngine = Depends(get_engine),
):
    """Update risk limits."""
    try:
        await engine.update_risk_limit(
            limit_name=limit_update.name,
            limit_value=limit_update.limit_value,
        )

        return {
            "message": f"Risk limit {limit_update.name} updated",
            "new_value": limit_update.limit_value,
            "timestamp": datetime.utcnow(),
        }

    except Exception as e:
        logger.error(f"Error updating risk limit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update risk limit",
        )


@router.get("/risk/circuit-breaker", response_model=CircuitBreakerStatus)
async def get_circuit_breaker_status(
    engine: TradingEngine = Depends(get_engine),
):
    """Get circuit breaker status."""
    try:
        circuit_breaker = engine.circuit_breaker

        status_str = "inactive"
        if circuit_breaker.triggered:
            status_str = "cooldown" if circuit_breaker.is_in_cooldown else "active"

        return CircuitBreakerStatus(
            active=circuit_breaker.triggered,
            triggered_at=circuit_breaker.triggered_at,
            reason=circuit_breaker.triggered_reason,
            triggered_by_metric=circuit_breaker.triggered_by_metric,
            reset_in_seconds=circuit_breaker.reset_in_seconds,
            status=status_str,
        )

    except Exception as e:
        logger.error(f"Error fetching circuit breaker status: {e}", exc_info=True)
        return {
            "active": False, "triggered_at": None, "reason": None,
            "triggered_by_metric": None, "reset_in_seconds": None,
            "status": "inactive",
        }


@router.post("/risk/circuit-breaker/reset", status_code=status.HTTP_200_OK)
async def reset_circuit_breaker(
    engine: TradingEngine = Depends(get_engine),
):
    """Reset circuit breaker (admin action)."""
    try:
        await engine.reset_circuit_breaker()

        return {
            "message": "Circuit breaker reset",
            "timestamp": datetime.utcnow(),
        }

    except Exception as e:
        logger.error(f"Error resetting circuit breaker: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset circuit breaker",
        )


@router.get("/risk/alerts", response_model=RiskAlertListResponse)
async def get_risk_alerts(
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Get recent risk alerts."""
    try:
        from core.database import AsyncSessionLocal
        from core.models import Alert as RiskAlertModel
        from sqlalchemy import and_, select

        async with AsyncSessionLocal() as db:
            query = select(RiskAlertModel).order_by(RiskAlertModel.timestamp.desc()).limit(limit)

            filters = []
            if severity:
                filters.append(RiskAlertModel.severity == severity)
            if acknowledged is not None:
                filters.append(RiskAlertModel.acknowledged == acknowledged)

            if filters:
                query = query.where(and_(*filters))

            alerts = (await db.execute(query)).scalars().all()

            alert_responses = [
                RiskAlert(
                    id=a.id,
                    severity=a.severity,
                    message=a.message,
                    metric=a.metric,
                    value=a.value,
                    threshold=a.threshold,
                    timestamp=a.timestamp,
                    acknowledged=a.acknowledged,
                )
                for a in alerts
            ]

            critical = sum(1 for a in alert_responses if a.severity == "critical")
            high = sum(1 for a in alert_responses if a.severity == "high")
            medium = sum(1 for a in alert_responses if a.severity == "medium")

            return RiskAlertListResponse(
                alerts=alert_responses,
                total=len(alert_responses),
                critical=critical,
                high=high,
                medium=medium,
            )

    except Exception as e:
        logger.error(f"Error fetching risk alerts: {e}", exc_info=True)
        return {"alerts": [], "total": 0, "critical": 0, "high": 0, "medium": 0}
