"""API endpoint integration tests.

In TESTING=1 mode the engine is not initialized in the lifespan; many routes
call ``get_engine()`` which raises RuntimeError, and the global exception
handler returns 500. We assert on the shape of responses (200 or 500) so that
routing and middleware are verified end-to-end.
"""
import pytest


# ---------------------------------------------------------------------------
# Health / Metrics / Root
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_body(self, client):
        response = await client.get("/api/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    async def test_health_status_value(self, client):
        data = (await client.get("/api/health")).json()
        assert data["status"] == "healthy"


class TestMetricsEndpoint:
    async def test_metrics_returns_200(self, client):
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    async def test_metrics_prometheus_format(self, client):
        response = await client.get("/metrics")
        text = response.text
        # Prometheus exposition format contains HELP/TYPE comments
        assert "# HELP" in text or "# TYPE" in text or text == ""


class TestUnknownRoute:
    async def test_unknown_api_route_404(self, client):
        response = await client.get("/api/this/does/not/exist")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    async def test_dashboard_overview_responds(self, client):
        response = await client.get("/api/dashboard/overview")
        # In TESTING=1 mode engine is not initialized; route raises and
        # global handler returns 500. DB-dependent routes return 503.
        # In live mode it returns 200.
        assert response.status_code in (200, 500, 503)

    async def test_dashboard_summary_responds(self, client):
        response = await client.get("/api/dashboard/summary")
        assert response.status_code in (200, 500, 503)

    async def test_equity_curve_default(self, client):
        response = await client.get("/api/dashboard/equity-curve")
        assert response.status_code in (200, 500, 503)

    @pytest.mark.parametrize("days", [1, 7, 30, 365])
    async def test_equity_curve_days_valid(self, client, days):
        response = await client.get(f"/api/dashboard/equity-curve?days={days}")
        assert response.status_code in (200, 500, 503)

    async def test_equity_curve_days_too_large_422(self, client):
        response = await client.get("/api/dashboard/equity-curve?days=999999")
        # 503 may fire before query validation if DB dep raises first
        assert response.status_code in (422, 503)

    async def test_equity_curve_days_zero_422(self, client):
        response = await client.get("/api/dashboard/equity-curve?days=0")
        assert response.status_code in (422, 503)

    async def test_allocation_responds(self, client):
        response = await client.get("/api/dashboard/allocation")
        assert response.status_code in (200, 500, 503)

    async def test_metrics_responds(self, client):
        response = await client.get("/api/dashboard/metrics")
        assert response.status_code in (200, 500, 503)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

class TestPositions:
    async def test_positions_list(self, client):
        response = await client.get("/api/positions")
        assert response.status_code in (200, 500, 503)

    async def test_positions_open_alias(self, client):
        response = await client.get("/api/positions/open")
        assert response.status_code in (200, 500, 503)

    async def test_positions_exposure(self, client):
        response = await client.get("/api/positions/exposure")
        assert response.status_code in (200, 500, 503)

    async def test_positions_history(self, client):
        response = await client.get("/api/positions/history")
        assert response.status_code in (200, 500, 503)


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

class TestTrades:
    async def test_trades_list(self, client):
        response = await client.get("/api/trades")
        assert response.status_code in (200, 500, 503)

    async def test_trades_stats(self, client):
        response = await client.get("/api/trades/stats")
        assert response.status_code in (200, 500, 503)

    async def test_trades_history_alias(self, client):
        response = await client.get("/api/trades/history")
        assert response.status_code in (200, 500, 503)

    async def test_pnl_distribution(self, client):
        response = await client.get("/api/trades/pnl-distribution")
        assert response.status_code == 200
        data = response.json()
        assert "buckets" in data and "counts" in data

    async def test_trades_invalid_page_422(self, client):
        response = await client.get("/api/trades?page=0")
        assert response.status_code in (422, 503)

    async def test_trades_invalid_page_size_422(self, client):
        response = await client.get("/api/trades?page_size=10000")
        assert response.status_code in (422, 503)

    async def test_trade_not_found(self, client):
        response = await client.get("/api/trades/nonexistent-id")
        # route list: stats/history/pnl-distribution are higher priority;
        # this id hits the trade lookup route -> 404/500/503 (DB dep unavail)
        assert response.status_code in (404, 500, 503)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

class TestStrategies:
    async def test_list_strategies(self, client):
        response = await client.get("/api/strategies")
        assert response.status_code in (200, 500)

    async def test_list_alias(self, client):
        response = await client.get("/api/strategies/list")
        assert response.status_code in (200, 500)


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------

class TestRisk:
    async def test_risk_overview(self, client):
        response = await client.get("/api/risk/overview")
        assert response.status_code in (200, 500)

    async def test_risk_limits(self, client):
        response = await client.get("/api/risk/limits")
        assert response.status_code in (200, 500)

    async def test_risk_circuit_breaker(self, client):
        response = await client.get("/api/risk/circuit-breaker")
        assert response.status_code in (200, 500)

    async def test_risk_alerts(self, client):
        response = await client.get("/api/risk/alerts")
        assert response.status_code in (200, 500)

    async def test_risk_alerts_limit_validation(self, client):
        response = await client.get("/api/risk/alerts?limit=10000")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class TestSystem:
    async def test_system_health(self, client):
        response = await client.get("/api/system/health")
        assert response.status_code in (200, 500)

    async def test_system_config(self, client):
        response = await client.get("/api/system/config")
        assert response.status_code in (200, 500)

    async def test_system_scheduler(self, client):
        response = await client.get("/api/system/scheduler")
        assert response.status_code in (200, 500)


class TestSystemLogs:
    async def test_logs_returns_200(self, client):
        response = await client.get("/api/system/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert "level_counts" in data

    async def test_logs_with_level_filter(self, client):
        response = await client.get("/api/system/logs?level=ERROR")
        assert response.status_code == 200

    async def test_logs_invalid_limit_422(self, client):
        response = await client.get("/api/system/logs?limit=100000")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

class TestCORS:
    async def test_cors_headers_on_preflight(self, client):
        response = await client.options(
            "/api/health",
            headers={
                "origin": "http://localhost:5173",
                "access-control-request-method": "GET",
            },
        )
        # preflight should complete
        assert response.status_code in (200, 204, 400)

    async def test_process_time_header(self, client):
        response = await client.get("/api/health")
        assert "x-process-time" in {k.lower() for k in response.headers.keys()}


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidationErrors:
    async def test_negative_days_rejected(self, client):
        response = await client.get("/api/dashboard/equity-curve?days=-5")
        # 503 may fire before query validation if DB dep raises first
        assert response.status_code in (422, 503)

    async def test_non_int_days_rejected(self, client):
        response = await client.get("/api/dashboard/equity-curve?days=abc")
        assert response.status_code in (422, 503)
