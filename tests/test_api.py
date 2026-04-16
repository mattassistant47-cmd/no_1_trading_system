"""API endpoint integration tests."""
import pytest


class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_body(self, client):
        response = await client.get("/api/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestMetricsEndpoint:
    async def test_metrics_returns_200(self, client):
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


class TestSystemLogs:
    async def test_logs_returns_200(self, client):
        response = await client.get("/api/system/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        assert "level_counts" in data
