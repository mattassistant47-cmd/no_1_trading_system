# No.1 Trading System

Autonomous multi-asset trading system with self-evolution capabilities.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    NGINX (Port 80)                       │
│              Reverse Proxy + Rate Limiting                │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (Port 8000)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │Dashboard │ │ Trades   │ │Strategies│ │   Risk     │ │
│  │  API     │ │  API     │ │   API    │ │   API      │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
│  ┌──────────────────────────────────────────────────┐   │
│  │            WebSocket (Real-time Updates)          │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   Trading Engine                         │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────────┐│
│  │  Brokers   │ │ Strategies │ │   Risk Management    ││
│  │ Alpaca     │ │ Momentum   │ │ Position Sizing      ││
│  │ IBKR       │ │ MeanRev    │ │ Circuit Breaker      ││
│  │ Polymarket │ │ Crypto     │ │ Exposure Limits      ││
│  │            │ │ Options    │ │                      ││
│  │            │ │ Polymarket │ │                      ││
│  │            │ │ Ensemble   │ │                      ││
│  └────────────┘ └────────────┘ └──────────────────────┘│
│  ┌────────────────────────────────────────────────────┐ │
│  │              Self-Evolution Engine                  │ │
│  │  Optuna Optimizer | Walk-Forward | Strategy Rotator │ │
│  └────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │              Autonomous Agents                     │ │
│  │  Scanner | Rebalancer | Health Monitor | Reporter  │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│          PostgreSQL + TimescaleDB                        │
│    OHLCV | Trades | Positions | Signals | Performance    │
└─────────────────────────────────────────────────────────┘
```

## Supported Markets

| Market | Broker | Assets | Status |
|--------|--------|--------|--------|
| US Equities | Alpaca | Stocks, ETFs | Ready |
| Crypto | Alpaca | BTC, ETH, SOL, AVAX, LINK | Ready |
| Options | IBKR | Puts, Calls, Spreads | Requires IBKR account |
| Predictions | Polymarket | Binary events | Requires Polymarket wallet |

## Strategies

| Strategy | Target Return | Asset Class | Description |
|----------|--------------|-------------|-------------|
| Multi-Timeframe Momentum | 15-20% | Equities | RSI + MACD + ADX trend following |
| Statistical Mean Reversion | 15-18% | Equities | Bollinger Bands + Z-score reversion |
| Crypto Momentum | 25-35% | Crypto | Volume-weighted + BTC dominance filter |
| Options Wheel | 20-25% | Options | Cash-secured puts + covered calls |
| Polymarket Arbitrage | 15-25% | Predictions | Edge detection + Kelly sizing |
| Ensemble | 20-30% | All | Signal aggregation + regime rotation |

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/mattassistant47-cmd/no_1_trading_system.git
cd no_1_trading_system
cp .env.example .env
# Edit .env with your API keys
```

### 2. Deploy to OCI (Production)

```bash
# One-time setup on OCI instance
scp setup_oci.sh oci:~/
ssh oci "chmod +x setup_oci.sh && ./setup_oci.sh"

# Deploy
ssh oci
cd /opt/trading
git clone https://github.com/mattassistant47-cmd/no_1_trading_system.git .
cp .env.example .env
nano .env  # Add your API keys
docker compose up -d
```

### 3. Local development

```bash
# Backend
pip install -r requirements.txt
python main.py --mode paper --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### 4. Access

- Dashboard: http://your-oci-ip (nginx) or http://localhost:5173 (dev)
- API Docs: http://your-oci-ip:8000/docs
- Metrics: http://your-oci-ip:8000/metrics

## Risk Controls

- Max single position: 5% of portfolio
- Max daily loss: 2% of portfolio
- Max drawdown: 10% before circuit breaker triggers
- Max leverage: 1.5x
- Asset class limits: Equities 50%, Crypto 20%, Options 20%, Predictions 10%
- Circuit breaker: Graduated response (warning -> reduce -> halt -> liquidate)
- Dead man's switch: Auto-halt if no heartbeat for 5 minutes

## Self-Evolution

The system continuously improves through:

- Optuna optimization: Bayesian parameter tuning weekly
- Walk-forward analysis: Rolling train/validate/test windows
- Strategy rotation: Dynamic weight adjustment based on rolling Sharpe
- Regime detection: Bull/bear/sideways classification affects strategy weights
- Alpha decay detection: Auto-disables strategies losing edge

## Project Structure

```
├── main.py                 # Entry point
├── config/                 # Settings and strategy YAML
├── core/                   # Engine, models, database, events
├── api/                    # FastAPI routes and WebSocket
├── brokers/                # Alpaca, IBKR, Polymarket adapters
├── data/                   # Market data feeds (Alpaca, CoinGecko, FRED)
├── strategies/             # Trading strategies + ensemble
├── risk/                   # Risk management + circuit breaker
├── evolution/              # Optimizer, walk-forward, rotator
├── agents/                 # Scanner, rebalancer, health, reporter
├── frontend/               # React dashboard (dark factory theme)
├── tests/                  # Pytest suite
├── docker-compose.yml      # Full stack orchestration
├── Dockerfile              # Multi-stage build
├── nginx.conf              # Reverse proxy config
├── setup_oci.sh            # OCI one-time setup
├── deploy.sh               # Deployment script
└── .github/workflows/      # CI/CD pipelines
```

## Paper Trading Phase (Weeks 1-2)

Week 1: Deploy with Alpaca paper trading. Monitor all strategies. Collect baseline metrics.

Week 2: Run Optuna optimization. Adjust parameters. Evaluate walk-forward results. Fine-tune risk limits.

Target: Validate 20-30% annualized return potential before switching to live.

## Environment

- Runtime: OCI ARM Free Tier (4 CPU, 24GB RAM)
- Database: PostgreSQL 16 + TimescaleDB
- Frontend: React + Vite + Tailwind (dark factory mode)
- CI/CD: GitHub Actions (free tier optimized)
