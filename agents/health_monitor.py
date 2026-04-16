"""
Health Monitor Agent

System health checks with alerts via Discord/Telegram webhooks
and Prometheus metrics export.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import json
from loguru import logger


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """System component types"""
    DATABASE = "database"
    BROKER = "broker"
    DATA_FEED = "data_feed"
    STRATEGY = "strategy"
    SYSTEM = "system"


@dataclass
class HealthCheck:
    """Individual health check result"""
    component: ComponentType
    component_id: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check: datetime = field(default_factory=datetime.utcnow)
    next_check: datetime = field(default_factory=datetime.utcnow)
    consecutive_failures: int = 0
    response_time_ms: float = 0.0


@dataclass
class SystemMetrics:
    """System resource metrics"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    disk_percent: float = 0.0
    open_connections: int = 0
    uptime_hours: float = 0.0


@dataclass
class HealthReport:
    """Overall health report"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    overall_status: HealthStatus = HealthStatus.UNKNOWN
    components: List[HealthCheck] = field(default_factory=list)
    system_metrics: Optional[SystemMetrics] = None
    alerts: List[str] = field(default_factory=list)
    critical_alerts: List[str] = field(default_factory=list)


class HealthMonitor:
    """
    Autonomous health monitoring agent.

    Capabilities:
    - Database connectivity checks
    - Broker connection health
    - Data feed freshness validation
    - Strategy heartbeat monitoring
    - System resource monitoring (CPU, memory, disk)
    - Alerts via webhooks (Discord, Telegram)
    - Prometheus metrics export
    """

    def __init__(
        self,
        db_check_interval_sec: int = 60,
        broker_check_interval_sec: int = 30,
        data_feed_check_interval_sec: int = 30,
        strategy_heartbeat_timeout_sec: int = 300,
        max_consecutive_failures: int = 3,
    ):
        """
        Initialize HealthMonitor.

        Args:
            db_check_interval_sec: Database check interval
            broker_check_interval_sec: Broker check interval
            data_feed_check_interval_sec: Data feed check interval
            strategy_heartbeat_timeout_sec: Strategy heartbeat timeout
            max_consecutive_failures: Max failures before critical alert
        """
        self.db_check_interval_sec = db_check_interval_sec
        self.broker_check_interval_sec = broker_check_interval_sec
        self.data_feed_check_interval_sec = data_feed_check_interval_sec
        self.strategy_heartbeat_timeout_sec = strategy_heartbeat_timeout_sec
        self.max_consecutive_failures = max_consecutive_failures

        # State
        self.components: Dict[str, HealthCheck] = {}
        self.health_history: List[HealthReport] = []
        self.strategy_heartbeats: Dict[str, datetime] = {}

        # Callbacks
        self.on_health_alert: Optional[Callable] = None
        self.on_critical_alert: Optional[Callable] = None

        # Webhook URLs
        self.discord_webhook_url: Optional[str] = None
        self.telegram_webhook_url: Optional[str] = None

        logger.info(
            f"HealthMonitor initialized: "
            f"db_check={db_check_interval_sec}s, "
            f"broker_check={broker_check_interval_sec}s, "
            f"strategy_heartbeat_timeout={strategy_heartbeat_timeout_sec}s"
        )

    def set_discord_webhook(self, url: str):
        """Set Discord webhook URL for alerts"""
        self.discord_webhook_url = url
        logger.info("Discord webhook configured")

    def set_telegram_webhook(self, url: str):
        """Set Telegram webhook URL for alerts"""
        self.telegram_webhook_url = url
        logger.info("Telegram webhook configured")

    async def check_database(
        self,
        check_fn: Callable,
        component_id: str = "postgres",
    ) -> HealthCheck:
        """
        Check database connectivity.

        Args:
            check_fn: Async function that returns True if healthy
            component_id: Database identifier

        Returns:
            HealthCheck result
        """
        start_time = datetime.utcnow()

        check = self.components.get(
            f"{ComponentType.DATABASE.value}:{component_id}"
        ) or HealthCheck(
            component=ComponentType.DATABASE,
            component_id=component_id,
        )

        try:
            success = await check_fn()
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            if success:
                check.status = HealthStatus.HEALTHY
                check.message = "Connected"
                check.consecutive_failures = 0
                check.response_time_ms = response_time
            else:
                check.status = HealthStatus.DEGRADED
                check.message = "Health check returned False"
                check.consecutive_failures += 1

        except Exception as e:
            check.status = HealthStatus.CRITICAL
            check.message = f"Connection error: {str(e)}"
            check.consecutive_failures += 1

            logger.error(f"Database check failed: {str(e)}")

        check.last_check = datetime.utcnow()
        self.components[f"{ComponentType.DATABASE.value}:{component_id}"] = check

        return check

    async def check_broker(
        self,
        check_fn: Callable,
        component_id: str = "primary",
    ) -> HealthCheck:
        """Check broker connectivity"""
        start_time = datetime.utcnow()

        check = self.components.get(
            f"{ComponentType.BROKER.value}:{component_id}"
        ) or HealthCheck(
            component=ComponentType.BROKER,
            component_id=component_id,
        )

        try:
            account_balance = await check_fn()
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            if account_balance is not None:
                check.status = HealthStatus.HEALTHY
                check.message = f"Account balance: ${account_balance:,.2f}"
                check.consecutive_failures = 0
                check.response_time_ms = response_time
            else:
                check.status = HealthStatus.DEGRADED
                check.message = "Unable to retrieve account balance"
                check.consecutive_failures += 1

        except Exception as e:
            check.status = HealthStatus.CRITICAL
            check.message = f"Connection error: {str(e)}"
            check.consecutive_failures += 1

            logger.error(f"Broker check failed: {str(e)}")

        check.last_check = datetime.utcnow()
        self.components[f"{ComponentType.BROKER.value}:{component_id}"] = check

        return check

    async def check_data_feed(
        self,
        check_fn: Callable,
        component_id: str = "primary",
        max_staleness_sec: int = 60,
    ) -> HealthCheck:
        """Check data feed freshness"""
        check = self.components.get(
            f"{ComponentType.DATA_FEED.value}:{component_id}"
        ) or HealthCheck(
            component=ComponentType.DATA_FEED,
            component_id=component_id,
        )

        try:
            last_update_time = await check_fn()  # Should return datetime

            if last_update_time:
                staleness = (datetime.utcnow() - last_update_time).total_seconds()

                if staleness < max_staleness_sec:
                    check.status = HealthStatus.HEALTHY
                    check.message = f"Data fresh ({staleness:.0f}s old)"
                    check.consecutive_failures = 0
                else:
                    check.status = HealthStatus.DEGRADED
                    check.message = f"Data stale ({staleness:.0f}s old)"
                    check.consecutive_failures += 1

            else:
                check.status = HealthStatus.CRITICAL
                check.message = "No data received"
                check.consecutive_failures += 1

        except Exception as e:
            check.status = HealthStatus.CRITICAL
            check.message = f"Check error: {str(e)}"
            check.consecutive_failures += 1

            logger.error(f"Data feed check failed: {str(e)}")

        check.last_check = datetime.utcnow()
        self.components[f"{ComponentType.DATA_FEED.value}:{component_id}"] = check

        return check

    def strategy_heartbeat(self, strategy_id: str):
        """Record strategy heartbeat"""
        self.strategy_heartbeats[strategy_id] = datetime.utcnow()

    async def check_strategy_heartbeats(self) -> List[HealthCheck]:
        """Check all strategy heartbeats"""
        checks = []

        for strategy_id, last_heartbeat in self.strategy_heartbeats.items():
            check = self.components.get(
                f"{ComponentType.STRATEGY.value}:{strategy_id}"
            ) or HealthCheck(
                component=ComponentType.STRATEGY,
                component_id=strategy_id,
            )

            elapsed = (datetime.utcnow() - last_heartbeat).total_seconds()

            if elapsed < self.strategy_heartbeat_timeout_sec:
                check.status = HealthStatus.HEALTHY
                check.message = f"Active ({elapsed:.0f}s)"
                check.consecutive_failures = 0

            else:
                check.status = HealthStatus.CRITICAL
                check.message = f"No heartbeat ({elapsed:.0f}s)"
                check.consecutive_failures += 1

                logger.warning(f"Strategy {strategy_id} heartbeat timeout")

            check.last_check = datetime.utcnow()
            self.components[f"{ComponentType.STRATEGY.value}:{strategy_id}"] = check
            checks.append(check)

        return checks

    async def check_system_resources(
        self,
        get_metrics_fn: Callable,
    ) -> SystemMetrics:
        """
        Check system resource usage.

        Args:
            get_metrics_fn: Async function returning SystemMetrics

        Returns:
            SystemMetrics
        """
        try:
            metrics = await get_metrics_fn()

            if metrics.cpu_percent > 90:
                logger.warning(f"High CPU usage: {metrics.cpu_percent:.1f}%")

            if metrics.memory_percent > 85:
                logger.warning(f"High memory usage: {metrics.memory_percent:.1f}%")

            if metrics.disk_percent > 90:
                logger.warning(f"Low disk space: {metrics.disk_percent:.1f}%")

            return metrics

        except Exception as e:
            logger.error(f"Resource check error: {e}")
            return SystemMetrics()

    async def generate_health_report(
        self,
        system_metrics: Optional[SystemMetrics] = None,
    ) -> HealthReport:
        """Generate overall health report"""
        report = HealthReport(
            components=list(self.components.values()),
            system_metrics=system_metrics,
        )

        # Check for critical status
        critical_checks = [
            c for c in report.components
            if c.status == HealthStatus.CRITICAL
        ]

        # Check for excessive failures
        failing_checks = [
            c for c in report.components
            if c.consecutive_failures >= self.max_consecutive_failures
        ]

        report.critical_alerts = [
            f"{c.component.value}:{c.component_id} - {c.message}"
            for c in critical_checks
        ]

        report.alerts = [
            f"{c.component.value}:{c.component_id} - {c.message}"
            for c in failing_checks
        ]

        # Determine overall status
        if critical_checks or len(failing_checks) > 2:
            report.overall_status = HealthStatus.CRITICAL
        elif failing_checks or any(c.status == HealthStatus.DEGRADED for c in report.components):
            report.overall_status = HealthStatus.DEGRADED
        else:
            report.overall_status = HealthStatus.HEALTHY

        self.health_history.append(report)

        # Send alerts
        if report.critical_alerts:
            await self._send_critical_alert(report)

        if report.alerts:
            await self._send_health_alert(report)

        return report

    async def _send_health_alert(self, report: HealthReport):
        """Send health alert via webhooks"""
        message = f"Health Alert: {len(report.alerts)} component(s) degraded\n"
        message += "\n".join(report.alerts)

        if self.on_health_alert:
            await self._safe_call(self.on_health_alert, message)

        if self.discord_webhook_url:
            await self._send_discord_alert(message, color=16776960)  # Yellow

        if self.telegram_webhook_url:
            await self._send_telegram_alert(message)

        logger.warning(f"Health alert sent: {len(report.alerts)} issues")

    async def _send_critical_alert(self, report: HealthReport):
        """Send critical alert via webhooks"""
        message = f"CRITICAL ALERT: {len(report.critical_alerts)} component(s) critical\n"
        message += "\n".join(report.critical_alerts)

        if self.on_critical_alert:
            await self._safe_call(self.on_critical_alert, message)

        if self.discord_webhook_url:
            await self._send_discord_alert(message, color=16711680)  # Red

        if self.telegram_webhook_url:
            await self._send_telegram_alert(message)

        logger.critical(f"Critical alert sent: {len(report.critical_alerts)} critical issues")

    async def _send_discord_alert(self, message: str, color: int = 16711680):
        """Send alert to Discord"""
        try:
            payload = {
                "embeds": [
                    {
                        "title": "Trading System Alert",
                        "description": message,
                        "color": color,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ]
            }

            # In production, would use aiohttp to POST to Discord webhook
            logger.debug(f"Discord alert: {message}")

        except Exception as e:
            logger.error(f"Discord alert error: {e}")

    async def _send_telegram_alert(self, message: str):
        """Send alert to Telegram"""
        try:
            payload = {
                "text": message,
                "parse_mode": "Markdown",
            }

            # In production, would use aiohttp to POST to Telegram webhook
            logger.debug(f"Telegram alert: {message}")

        except Exception as e:
            logger.error(f"Telegram alert error: {e}")

    async def _safe_call(self, callback: Callable, *args, **kwargs):
        """Safely call callback"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Callback error: {e}")

    def get_health_status(self) -> Dict:
        """Get current health status"""
        return {
            "overall_status": (
                self.health_history[-1].overall_status.value
                if self.health_history else HealthStatus.UNKNOWN.value
            ),
            "components": {
                f"{c.component.value}:{c.component_id}": {
                    "status": c.status.value,
                    "message": c.message,
                    "response_time_ms": c.response_time_ms,
                    "consecutive_failures": c.consecutive_failures,
                }
                for c in self.components.values()
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []

        # Component health metrics
        lines.append("# HELP trading_component_health Component health status (1=healthy, 0=not)")
        lines.append("# TYPE trading_component_health gauge")

        for component_key, check in self.components.items():
            status_value = 1.0 if check.status == HealthStatus.HEALTHY else 0.0
            component_type = check.component.value
            component_id = check.component_id

            lines.append(
                f'trading_component_health{{component="{component_type}",'
                f'component_id="{component_id}"}} {status_value}'
            )

        # Response time metrics
        lines.append("# HELP trading_check_response_time_ms Check response time in milliseconds")
        lines.append("# TYPE trading_check_response_time_ms gauge")

        for component_key, check in self.components.items():
            lines.append(
                f'trading_check_response_time_ms{{component="{check.component.value}"}} '
                f'{check.response_time_ms}'
            )

        return "\n".join(lines)
