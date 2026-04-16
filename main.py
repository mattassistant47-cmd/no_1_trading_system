#!/usr/bin/env python3
"""
No.1 Trading System - Main Entry Point
========================================
Autonomous multi-asset trading system with self-evolution capabilities.
Supports: US Equities, Crypto, Options, Prediction Markets
Brokers: Alpaca, IBKR, Polymarket
"""

import argparse
import os
import signal
import sys
from pathlib import Path

import uvicorn
from loguru import logger


def setup_logging(log_level: str = "INFO"):
    """Configure loguru logging with file rotation."""
    logger.remove()  # Remove default handler

    # Console output
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True,
    )

    # File output with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        str(log_dir / "trading_{time:YYYY-MM-DD}.log"),
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",      # New file daily
        retention="30 days",   # Keep 30 days
        compression="gz",      # Compress old logs
        enqueue=True,          # Thread-safe
    )

    # Error-only log
    logger.add(
        str(log_dir / "errors_{time:YYYY-MM-DD}.log"),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
        rotation="00:00",
        retention="90 days",
        compression="gz",
        enqueue=True,
    )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="No.1 Trading System - Autonomous Multi-Asset Trading"
    )
    parser.add_argument(
        "--mode", choices=["paper", "live"], default=None,
        help="Trading mode (overrides TRADING_MODE env var)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="API server port (default: 8000)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="API server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--workers", type=int, default=2,
        help="Number of uvicorn workers (default: 2)"
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--log-level", default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (overrides LOG_LEVEL env var)"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Set environment overrides
    if args.mode:
        os.environ["TRADING_MODE"] = args.mode
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level

    log_level = os.environ.get("LOG_LEVEL", "INFO")
    trading_mode = os.environ.get("TRADING_MODE", "paper")

    setup_logging(log_level)

    logger.info("=" * 60)
    logger.info("  No.1 Trading System - Starting Up")
    logger.info(f"  Mode: {trading_mode.upper()}")
    logger.info(f"  Host: {args.host}:{args.port}")
    logger.info(f"  Workers: {args.workers}")
    logger.info(f"  Log Level: {log_level}")
    logger.info("=" * 60)

    if trading_mode == "live":
        logger.warning("=" * 60)
        logger.warning("  ⚠️  LIVE TRADING MODE - REAL MONEY AT RISK  ⚠️")
        logger.warning("=" * 60)

    # Graceful shutdown handler
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Run the server
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
        log_level=log_level.lower(),
        access_log=True,
        server_header=False,
        date_header=False,
    )


if __name__ == "__main__":
    main()
