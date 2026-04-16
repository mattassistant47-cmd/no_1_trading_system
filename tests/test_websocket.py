"""WebSocket tests."""
import pytest
from starlette.testclient import TestClient


class TestWebSocket:
    def test_connect_and_receive_welcome(self, app):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert "timestamp" in data

    def test_ping_pong(self, app):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            _ = ws.receive_json()  # welcome
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_subscribe_to_channel(self, app):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            _ = ws.receive_json()  # welcome
            ws.send_json({"type": "subscribe", "channel": "portfolio"})
            data = ws.receive_json()
            assert data["type"] == "subscription_confirmed"
            assert data["channel"] == "portfolio"

    def test_unknown_message_type(self, app):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            _ = ws.receive_json()  # welcome
            ws.send_json({"type": "invalid_type"})
            data = ws.receive_json()
            assert data["type"] == "error"
