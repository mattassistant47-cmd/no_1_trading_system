# No.1 Trading System

## Stack
- Backend: Python 3.11, FastAPI, SQLAlchemy 2.0 async, TimescaleDB, APScheduler
- Frontend: React 18, Vite 5, Tailwind CSS 3, Recharts
- Infra: Docker Compose (separate frontend/backend), Nginx reverse proxy, OCI ARM64

## OCI Deployment
- SSH: `ssh oci` (132.145.202.121, ubuntu, ~/Downloads/ssh-key-2026-04-06.key)
- Dev: ports 8001 (backend), 8080 (frontend), 5433 (db). Project name: `trading-dev`
- Prod: ports 8000 (backend), 80 (frontend), 5432 (db). Project name: `trading-prod`
- VPN: WireGuard 10.8.0.1 (OCI) ↔ 10.8.0.2 (Mac Mini), port 51820
- **Always stop dev before deploying prod**: `docker compose -p trading-dev ... down` → deploy prod → verify → restart dev. Both share `--project-directory .` so explicit `--project-name` is required.
- Push to GitHub from OCI (SSH key works): `ssh oci "cd ~/trading-bot/code && git push origin main"`
- Local `gh auth` has TLS cert issues — don't waste time debugging, use OCI for GitHub ops.

## Code Gotchas
- `core/database.py:AsyncSessionLocal` is a mutable global. Import as `import core.database as _db` then use `_db.AsyncSessionLocal` — never `from core.database import AsyncSessionLocal` (captures None at import time).
- `core/models.py` uses `extra_metadata = Column("metadata", JSONB)` — the Python attr is `extra_metadata` because `metadata` is reserved by SQLAlchemy `Base`.
- `strategies/__init__.py` uses lazy imports with try/except — `pandas-ta` is unavailable on ARM64/Python 3.11.
- `risk/circuit_breaker.py` — typing imports must be at top of file (Dict was defined at EOF after first use).
- Route ordering in FastAPI matters: `/trades/stats` must be defined BEFORE `/trades/{trade_id}`.

## Frontend-Backend Contract
- Backend returns snake_case, frontend expects camelCase. Every component has a `snakeToCamel` helper.
- API responses wrap lists in objects: `{strategies: [...]}`, `{positions: [...]}`, `{trades: [...]}`.
- Frontend components must guard all `.toFixed()`, `.toLocaleString()`, `.map()` with `(value || 0)` / `(arr || [])`.

## Testing
- `pytest tests/ -m "not e2e"` — runs 90 unit/integration tests (SQLite in-memory, no DB needed)
- Tests run on OCI in `test-runner` container: `docker compose -p trading-dev --profile testing run --rm test-runner`
- E2E tests: `E2E=1 pytest tests/e2e/` (requires live stack)
- Set `TESTING=1` env var to skip engine init in FastAPI lifespan
- Set `ENVIRONMENT=development` (not `testing` — Settings validator only allows development/staging/production)

## Docker
- `Dockerfile.backend` — includes tests + scripts for test-runner container
- `frontend/Dockerfile` — Vite builds to `../static` (not `dist`), Dockerfile copies from `/static`
- `.dockerignore` must NOT exclude `tests/` (needed by test-runner)
- Log volume mounts cause PermissionError (appuser uid 1000 vs root-owned host dir) — removed from compose files
- OCI network interface is `enp0s6` (not `ens3`) — matters for WireGuard PostUp iptables rules

## Deploy Commands
- Sync code: `tar czf /tmp/bot.tar.gz --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='.env' . && scp /tmp/bot.tar.gz oci:/tmp/ && ssh oci "cd ~/trading-bot/code && tar xzf /tmp/bot.tar.gz && rm /tmp/bot.tar.gz && find . -name '._*' -delete"`
- Build: `ssh oci "cd ~/trading-bot/code && docker compose -p trading-dev -f ~/trading-bot/dev/docker-compose.dev.yml --env-file ~/trading-bot/dev/.env --project-directory . build backend frontend"`
- Start: same command but `up -d db backend frontend`
- Health: `curl -sf http://10.8.0.1:8001/api/health` (dev) / `http://10.8.0.1:8000/api/health` (prod)
