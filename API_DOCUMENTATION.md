# No.1 Trading System - API Documentation

## Overview

Complete FastAPI backend for the No.1 Trading System, a multi-asset autonomous trading platform with support for stocks, options, crypto, and prediction markets.

## Architecture

### File Structure

```
api/
├── __init__.py              # Package init
├── main.py                  # FastAPI application, lifespan, middleware
├── config.py                # Configuration & settings
├── deps.py                  # Dependency injection
├── exceptions.py            # Custom exceptions
├── middleware.py            # Middleware components
├── utils.py                 # Utility functions
├── websocket.py             # WebSocket handlers
└── routes/
    ├── __init__.py
    ├── dashboard.py         # Portfolio overview & metrics
    ├── trades.py            # Trade management
    ├── positions.py         # Position management
    ├── strategies.py        # Strategy management
    ├── risk.py              # Risk monitoring
    └── system.py            # System management
```

## Features

- **Multi-Asset Trading**: Stocks, options, crypto, prediction markets
- **Real-time Updates**: WebSocket for live portfolio, trades, signals
- **Risk Management**: VaR, drawdown, exposure monitoring
- **Strategy Management**: Enable/disable, parameter tuning, backtesting
- **Trade Management**: View, filter, close positions, manual trades
- **System Monitoring**: Health checks, logs, scheduler status
- **Broker Integration**: Alpaca, Interactive Brokers, Polymarket
- **Prometheus Metrics**: Full observability with `/metrics` endpoint

## API Endpoints

### Dashboard Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/summary` | Portfolio value, P&L, metrics |
| GET | `/api/dashboard/equity-curve` | Historical equity curve |
| GET | `/api/dashboard/allocation` | Asset allocation breakdown |
| GET | `/api/dashboard/metrics` | Performance metrics (Sharpe, drawdown, etc.) |

### Trade Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trades` | List trades with filtering & pagination |
| GET | `/api/trades/{id}` | Single trade details |
| GET | `/api/trades/stats` | Trade statistics (win rate, profit factor) |
| POST | `/api/trades/manual` | Submit manual trade override |

### Position Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/positions` | Current open positions |
| GET | `/api/positions/history` | Historical closed positions |
| POST | `/api/positions/{id}/close` | Close position manually |
| GET | `/api/positions/exposure` | Exposure by sector/strategy/asset class |

### Strategy Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/strategies` | List all strategies with status |
| GET | `/api/strategies/{name}` | Detailed strategy info |
| POST | `/api/strategies/{name}/enable` | Enable strategy |
| POST | `/api/strategies/{name}/disable` | Disable strategy |
| PUT | `/api/strategies/{name}/params` | Update parameters |
| GET | `/api/strategies/{name}/signals` | Recent signals |
| POST | `/api/strategies/{name}/backtest` | Run backtest (async) |

### Risk Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/risk/overview` | Risk dashboard (VaR, drawdown, exposure) |
| GET | `/api/risk/limits` | Current risk limits & usage |
| PUT | `/api/risk/limits` | Update risk limits |
| GET | `/api/risk/circuit-breaker` | Circuit breaker status |
| POST | `/api/risk/circuit-breaker/reset` | Reset circuit breaker |
| GET | `/api/risk/alerts` | Recent risk alerts |

### System Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/system/health` | System health checks |
| GET | `/api/system/logs` | Recent system logs |
| GET | `/api/system/config` | Current configuration (sanitized) |
| POST | `/api/system/mode` | Switch paper/live mode |
| GET | `/api/system/scheduler` | Scheduler status |
| POST | `/api/system/restart` | Restart engine (async) |

### Health & Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | API health check |
| GET | `/metrics` | Prometheus metrics |

## WebSocket

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

// Subscribe to portfolio updates
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'portfolio'
}));

// Listen for updates
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(message.type, message.data);
};
```

### Channels

- **portfolio**: Portfolio value, cash, P&L updates
- **trades**: New trades, trade closures
- **signals**: Strategy signals
- **alerts**: Risk alerts
- **system**: System status updates

### Messages

```json
{
  "type": "portfolio_update",
  "channel": "portfolio",
  "data": {
    "portfolio_value": 125000.50,
    "cash": 45000.00,
    "invested": 80000.50,
    "daily_pnl": 1500.50,
    "total_pnl": 25000.50,
    "daily_pnl_percentage": 1.23
  },
  "timestamp": "2024-01-15T14:30:00Z"
}
```

## Request/Response Examples

### Get Dashboard Summary

```bash
curl -X GET "http://localhost:8000/api/dashboard/summary" \
  -H "x-api-key: your-api-key"
```

Response:
```json
{
  "portfolio_value": 125000.50,
  "cash": 45000.00,
  "invested": 80000.50,
  "daily_pnl": 1500.50,
  "daily_pnl_percentage": 1.23,
  "total_pnl": 25000.50,
  "total_pnl_percentage": 25.00,
  "win_rate": 65.5,
  "sharpe_ratio": 2.15,
  "total_trades": 156,
  "open_positions": 8,
  "timestamp": "2024-01-15T14:30:00Z"
}
```

### Submit Manual Trade

```bash
curl -X POST "http://localhost:8000/api/trades/manual" \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key" \
  -d '{
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 10,
    "price": 180.50,
    "strategy": "manual",
    "comment": "Manual override"
  }'
```

Response:
```json
{
  "trade_id": "trade_abc123def456",
  "symbol": "AAPL",
  "side": "BUY",
  "quantity": 10,
  "price": 180.50,
  "status": "pending",
  "timestamp": "2024-01-15T14:30:00Z"
}
```

### List Trades with Filters

```bash
curl -X GET "http://localhost:8000/api/trades?page=1&page_size=20&symbol=AAPL&strategy=momentum" \
  -H "x-api-key: your-api-key"
```

Response:
```json
{
  "trades": [
    {
      "id": "trade_abc123",
      "symbol": "AAPL",
      "side": "BUY",
      "quantity": 10,
      "entry_price": 180.50,
      "entry_time": "2024-01-15T10:00:00Z",
      "exit_price": 185.75,
      "exit_time": "2024-01-15T14:00:00Z",
      "status": "closed",
      "pnl": 525.00,
      "pnl_percentage": 2.89,
      "strategy": "momentum",
      "broker": "alpaca"
    }
  ],
  "total": 156,
  "page": 1,
  "page_size": 20
}
```

## Configuration

### Environment Variables

```bash
# App
APP_NAME="No.1 Trading System API"
DEBUG=false

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# Security
REQUIRE_API_KEY=true
API_KEY_HEADER=x-api-key

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trading_system
DB_POOL_SIZE=20

# Trading
TRADING_MODE=paper
MAX_DAILY_LOSS=5000
MAX_POSITION_SIZE=100000
MAX_LEVERAGE=3.0
MAX_DRAWDOWN=25.0

# Brokers
ALPACA_ENABLED=true
IBKR_ENABLED=true
POLYMARKET_ENABLED=true

# Features
ENABLE_BACKTESTING=true
ENABLE_OPTIMIZATION=true
ENABLE_LIVE_TRADING=false

# Monitoring
PROMETHEUS_ENABLED=true
METRICS_PORT=9090
```

## Middleware

- **CORS**: Configurable cross-origin resource sharing
- **Request ID**: Unique ID for all requests (X-Request-ID header)
- **Logging**: Full request/response logging
- **Security Headers**: XSS protection, content-type protection, HSTS
- **Rate Limiting**: Simple per-IP rate limiting

## Error Handling

All errors follow standard HTTP status codes:

- **400 Bad Request**: Invalid input
- **401 Unauthorized**: Missing/invalid API key
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **409 Conflict**: Duplicate/conflicting resource
- **422 Unprocessable Entity**: Validation error
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Server error
- **503 Service Unavailable**: Service unavailable (broker, database)

Error response format:
```json
{
  "detail": "Error message",
  "status": 400,
  "request_id": "req_abc123"
}
```

## Authentication

API uses header-based key authentication (placeholder for expansion):

```bash
curl -H "x-api-key: your-api-key" http://localhost:8000/api/...
```

## Performance & Monitoring

### Prometheus Metrics

Access metrics at `/metrics`:

- `api_requests_total`: Total API requests by method, endpoint, status
- `api_request_duration_seconds`: Request duration histogram
- `trading_engine_portfolio_value`: Current portfolio value
- `trading_engine_trades_total`: Total trades executed
- `trading_engine_positions_open`: Number of open positions

### Logging

Logs include:
- Request/response tracing with request IDs
- Database query logging
- Trading events
- Broker communication
- Error tracking with full stack traces

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY api_requirements.txt .
RUN pip install -r api_requirements.txt

COPY . .

CMD ["python", "-m", "api.main"]
```

### Production

```bash
# Install dependencies
pip install -r api_requirements.txt

# Run with Gunicorn + Uvicorn
gunicorn api.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Or with direct Uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Development

```bash
# Install dev dependencies
pip install -r api_requirements.txt

# Run with auto-reload
python -m api.main

# Run tests
pytest tests/ -v

# Format code
black api/

# Lint
ruff check api/
```

## Integration with Core

The API is designed to integrate with the existing core modules:

- **core.engine**: TradingEngine for order execution
- **core.database**: Async SQLAlchemy for persistence
- **core.models**: Trade, Position, Strategy models
- **core.brokers**: Broker adapters (Alpaca, IBKR, Polymarket)
- **core.strategies**: Strategy implementations
- **core.risk**: Risk management and monitoring
- **core.events**: Event system for real-time updates

## WebSocket Architecture

The WebSocket system uses a centralized ConnectionManager that:

1. Maintains active client connections
2. Manages channel subscriptions per client
3. Broadcasts messages to subscribed clients
4. Handles connection/disconnection gracefully
5. Implements heartbeat for connection health

Broadcasts are triggered by core system events and sent to subscribers via helper functions.

## Security Considerations

1. **API Key**: Implement proper API key validation
2. **HTTPS**: Use HTTPS in production (with HSTS headers)
3. **CORS**: Configure CORS origins carefully
4. **Rate Limiting**: Implement proper rate limiting per API key
5. **Input Validation**: All inputs validated with Pydantic
6. **SQL Injection**: Protected via SQLAlchemy ORM
7. **Secrets**: Never commit secrets; use environment variables
8. **Logging**: Don't log sensitive data (API keys, tokens, account numbers)

## Support

For issues and questions, refer to the core module documentation and this API specification.
