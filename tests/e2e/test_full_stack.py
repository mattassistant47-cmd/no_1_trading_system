"""E2E tests - run against live dev stack on OCI."""
import os
import pytest
import httpx

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("E2E") != "1", reason="E2E tests disabled"),
]

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8001")


class TestFullStackHealth:
    async def test_api_health(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE}/api/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    async def test_metrics_endpoint(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE}/metrics")
            assert response.status_code == 200

    async def test_system_logs(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE}/api/system/logs")
            assert response.status_code == 200
