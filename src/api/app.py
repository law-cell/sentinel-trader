"""
FastAPI Application
===================
Main entry point for the SentinelTrader REST API.

Startup sequence:
    1. Connect to IB TWS
    2. Load rules from rules.json
    3. Start rule engine as a background asyncio task
    4. Serve API requests

Shutdown sequence:
    1. Cancel rule engine task
    2. Disconnect from IB

Usage:
    python run_api.py
    API docs: http://localhost:8000/docs
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.core.connection import IBConnection
from src.rules.engine import RuleEngine
from src.api.routes import rules as rules_router
from src.api.routes import account as account_router

RULES_FILE = Path("rules.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    conn = IBConnection()
    ib = None
    try:
        ib = await conn.connect()
        ib.reqMarketDataType(3)  # fallback to delayed data
        logger.info("IB connected")
    except Exception as e:
        logger.error(f"IB connection failed: {e} — account/market-data endpoints will return 503")

    engine = RuleEngine()
    engine_task = None

    if ib is not None and RULES_FILE.exists():
        engine.load_rules(RULES_FILE)
        if engine.all_rules:
            engine_task = asyncio.create_task(engine.run(ib, engine.symbols))
            logger.info("Rule engine started as background task")
        else:
            logger.warning("No rules loaded — engine not started")

    # Expose shared state to all request handlers via app.state
    app.state.ib = ib
    app.state.conn = conn
    app.state.engine = engine
    app.state.engine_task = engine_task

    logger.info("API server ready")
    yield  # ── Serving requests ──────────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if engine_task and not engine_task.done():
        engine_task.cancel()
        try:
            await engine_task
        except asyncio.CancelledError:
            pass

    conn.disconnect()
    logger.info("API server stopped")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SentinelTrader API",
    description=(
        "REST API for SentinelTrader.\n\n"
        "Manage rules, monitor your account, and view live market data."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rules_router.router)
app.include_router(account_router.router)


@app.get("/", tags=["health"])
async def health():
    """Health check — also confirms the server is running."""
    return {"status": "ok", "docs": "/docs"}
