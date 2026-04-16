"""
FastAPI application for No.1 Trading System.
Entry point for the backend API.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Counter, Histogram, generate_latest

from api.routes import dashboard, positions, risk, strategies, system, trades
from api.websocket import router as ws_router
from core.database import AsyncSessionLocal
from core.engine import TradingEngine

logger = logging.getLogger(__name__)

# Prometheus metrics
request_count = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)
request_duration = Histogram(
    "api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint"],
)

# Global state
_engine: Optional[TradingEngine] = None
_scheduler_task: Optional[asyncio.Task] = None


async def init_engine() -> TradingEngine:
    """Initialize the trading engine."""
    global _engine
    logger.info("Initializing trading engine...")

    try:
        _engine = TradingEngine()
        await _engine.initialize()
        logger.info("Trading engine initialized successfully")
        return _engine
    except Exception as e:
        logger.error(f"Failed to initialize trading engine: {e}", exc_info=True)
        raise


async def graceful_shutdown():
    """Gracefully shutdown all services."""
    logger.info("Initiating graceful shutdown...")

    global _engine, _scheduler_task

    try:
        if _scheduler_task and not _scheduler_task.done():
            _scheduler_task.cancel()
            try:
                await _scheduler_task
            except asyncio.CancelledError:
                logger.info("Scheduler shutdown complete")

        if _engine:
            await _engine.shutdown()
            logger.info("Trading engine shutdown complete")

        from core.database import teardown_database
        await teardown_database()
        logger.info("Database connections closed")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    import os

    if os.environ.get("TESTING") == "1":
        logger.info("Running in test mode - skipping engine initialization")
        yield
        return

    # Startup
    try:
        from core.database import setup_database
        await setup_database()
        engine = await init_engine()

        from api.deps import set_engine
        set_engine(engine)

        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    await graceful_shutdown()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="No.1 Trading System API",
        description="Multi-asset autonomous trading system backend",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    import os as _os
    cors_origins = _os.environ.get(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request timing middleware
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        import time

        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request processing error: {e}", exc_info=True)
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )

        process_time = time.time() - start_time
        endpoint = request.url.path

        request_count.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
        ).inc()

        request_duration.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(process_time)

        response.headers["X-Process-Time"] = str(process_time)
        return response

    # Exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # Health check endpoint
    @app.get("/api/health", tags=["Health"])
    async def health_check():
        """Check API health status."""
        return {
            "status": "healthy",
            "version": "1.0.0",
        }

    # Prometheus metrics endpoint
    @app.get("/metrics", tags=["Metrics"])
    async def metrics():
        """Prometheus metrics endpoint."""
        from fastapi.responses import Response
        return Response(
            content=generate_latest(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # Include routers
    app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
    app.include_router(trades.router, prefix="/api", tags=["Trades"])
    app.include_router(positions.router, prefix="/api", tags=["Positions"])
    app.include_router(strategies.router, prefix="/api", tags=["Strategies"])
    app.include_router(risk.router, prefix="/api", tags=["Risk"])
    app.include_router(system.router, prefix="/api", tags=["System"])
    app.include_router(ws_router)

    # Serve static frontend files (built by Vite into /app/static in Docker)
    static_path = Path(__file__).parent.parent / "static"
    if not static_path.exists():
        static_path = Path(__file__).parent.parent / "frontend" / "dist"
    if static_path.exists():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
