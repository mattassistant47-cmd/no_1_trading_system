"""Pytest configuration and shared fixtures."""
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["MODE"] = "paper"
os.environ["ENVIRONMENT"] = "development"
os.environ["TESTING"] = "1"
os.environ["ALPACA_API_KEY_PAPER"] = "test_key"
os.environ["ALPACA_API_SECRET_PAPER"] = "test_secret"
os.environ["FRED_API_KEY"] = "test_fred_key"
os.environ["LOG_LEVEL"] = "WARNING"

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def app():
    from api.main import create_app
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


class MockBroker:
    def __init__(self):
        self.positions = {}
        self.cash = 100000.0
        self.orders = []

    async def get_position(self, symbol):
        return self.positions.get(symbol, {"quantity": 0, "avg_fill_price": 0})

    async def place_order(self, symbol, quantity, price, side):
        order = {"id": len(self.orders) + 1, "symbol": symbol, "quantity": quantity, "price": price, "side": side}
        self.orders.append(order)
        return order

    async def get_cash(self):
        return self.cash


class MockMarketData:
    def __init__(self):
        self.prices = {"AAPL": 150.0, "MSFT": 300.0, "GOOGL": 140.0}

    async def get_price(self, symbol):
        return self.prices.get(symbol, 100.0)


@pytest.fixture
def mock_broker():
    return MockBroker()

@pytest.fixture
def mock_market_data():
    return MockMarketData()
