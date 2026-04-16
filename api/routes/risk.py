"""
Risk monitoring endpoints.
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


@router.get("/risk/overview", response_model=RiskOverview)
async def get_risk_overview(
    engine: TradingEngine = Depends(get_engine),
):
    """
    Get risk dashboard with VaR, drawdown, exposure, and limits.
    """
    try:
        var_95 = engine.var_95
        max_drawdown = engine.max_drawdown
        total_exposure = engine.total_exposure
        leverage = engine.leverage
        portfolio_heat = engine.portfolio_heat

        risk_metrics = [
            RiskMetric(
                name="Portfolio Heat",
                value=portfolio_heat,
                unit="%",
                status="red" if portfolio_heat > 80 else "yellow" if portfolio_heat > 50 else "green",
            ),
            RiskMetric(
                name="Leverage",
                value=leverage,
                unit="x",
                status="red" if leverage > 3 else "yellow" if leverage > 2 else "green",
                threshold=3.0,
            ),
            RiskMetric(
                name="Max Drawdown",
                value=abs(max_drawdown),
                unit="%",
                status="red" if abs(max_drawdown) > 20 else "yellow" if abs(max_drawdown) > 10 else "green",
                threshold=20.0,
            ),
        ]

        return RiskOverview(
            var_95=var_95,
            max_drawdown=max_drawdown,
            total_exposure=total_exposure,
            leverage=leverage,
            risk_metrics=risk_metrics,
            portfolio_heat=portfolio_heat,
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Error fetching risk overview: {e}", exc_info=True)
        return {
            "var_95": 0.0, "max_drawdown": 0.0, "total_exposure": 0.0,
            "leverage": 0.0, "risk_metrics": [], "portfolio_heat": 0.0,
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
                limit_value=3.0,
                limit_type="leverage",
                usage_percentage=(engine.leverage / 3.0 * 100),
                status="warning" if engine.leverage > 2.5 else "ok",
                description="Maximum portfolio leverage",
            ),
            RiskLimit(
                name="Max Drawdown",
                current_value=abs(engine.max_drawdown),
                limit_value=25.0,
                limit_type="drawdown",
                usage_percentage=(abs(engine.max_drawdown) / 25.0 * 100),
                status="violated" if abs(engine.max_drawdown) > 25 else "ok",
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
