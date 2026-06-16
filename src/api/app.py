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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.core.connection import IBConnection
from src.notifications.telegram import get_telegram_app
from src.orders.tracker import get_tracker
from src.rules.engine import RuleEngine
from src.api.routes import rules as rules_router
from src.api.routes import llm_rules as llm_rules_router
from src.api.routes import proposals as proposals_router
from src.api.routes import account as account_router

RULES_FILE = Path("rules.json")
STATIC_DIR = Path("web/dist")
PROPOSAL_EXPIRY_CHECK_INTERVAL_SECONDS = 30


async def _periodic_expiry() -> None:
    """Expire stale PENDING proposals every 30s, for users who never click approve/reject."""
    tracker = get_tracker()
    while True:
        await asyncio.sleep(PROPOSAL_EXPIRY_CHECK_INTERVAL_SECONDS)
        tracker.expire_stale()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    conn = IBConnection()
    engine = RuleEngine()
    engine_task = None

    # Register reconnect callback before the initial connect attempt so it is
    # in place whether the first connect succeeds, fails, or races to reconnect.
    async def on_reconnect(ib_instance) -> None:
        ib_instance.reqMarketDataType(1)
        logger.info("Reconnect callback: set market data type to real-time")
        if engine._stream is not None:
            await engine._stream.resubscribe_all()
            logger.info("Reconnect callback: resubscribed all market data streams")

    conn.set_reconnect_callback(on_reconnect)

    try:
        await conn.connect()
        # Type 1 = real-time (requires Master Client ID = IB_CLIENT_ID in TWS API settings)
        # Type 3 = delayed  (free, no subscription needed)
        # Type 4 = frozen   (last snapshot, works even with competing live session)
        conn.ib.reqMarketDataType(1)
        logger.info("IB connected")
    except Exception as e:
        logger.error(f"IB connection failed: {e} — will retry in background")
        # Initial connect failed — disconnectedEvent won't fire, so start reconnect manually
        asyncio.create_task(conn._reconnect_loop())
    ib = conn.ib  # always non-None; use ib.isConnected() to check live status

    tg = get_telegram_app()
    if tg is not None:
        await tg.start()

    if RULES_FILE.exists():
        engine.load_rules(RULES_FILE)

    if ib.isConnected():
        engine_task = asyncio.create_task(engine.run(ib, engine.symbols))
        logger.info("Rule engine started as background task")
    else:
        logger.warning("IB not connected at startup — engine will start on reconnect")

    expiry_task = asyncio.create_task(_periodic_expiry())
    logger.info("Proposal expiry background task started (every 30s)")

    # Expose shared state to all request handlers via app.state
    app.state.ib = ib
    app.state.conn = conn
    app.state.engine = engine
    app.state.engine_task = engine_task

    logger.info("API server ready")
    yield  # ── Serving requests ──────────────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    expiry_task.cancel()
    try:
        await expiry_task
    except asyncio.CancelledError:
        pass

    if engine_task and not engine_task.done():
        engine_task.cancel()
        try:
            await engine_task
        except asyncio.CancelledError:
            pass

    if tg is not None:
        await tg.stop()

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
app.include_router(llm_rules_router.router)
app.include_router(proposals_router.router)
app.include_router(account_router.router)


@app.get("/api/health", tags=["health"])
async def health():
    """Health check — returns IB connection status and subscribed symbols."""
    ib = getattr(app.state, "ib", None)
    ib_connected = bool(ib and ib.isConnected())
    engine = getattr(app.state, "engine", None)
    subscribed = list(engine._stream.subscriptions.keys()) if (engine and engine._stream) else []
    return {
        "status": "ok",
        "ib_connected": ib_connected,
        "subscribed_symbols": subscribed,
    }


# ─── Production static file serving ──────────────────────────────────────────
# Only active when web/dist exists (i.e. inside the Docker image).
# In development, Vite's dev server handles the frontend on port 5173.

if STATIC_DIR.exists():
    # Serve built JS/CSS/image assets
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    # SPA catch-all: any path not matched by an API route returns index.html.
    # Must be registered LAST so API routes take priority.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        return FileResponse(STATIC_DIR / "index.html")
