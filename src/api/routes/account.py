"""
Account API Routes
==================
Endpoints for account data, positions, and live market snapshots.

Endpoints:
    GET /api/account              — account summary (NetLiq, BuyingPower, etc.)
    GET /api/positions            — current open positions
    GET /api/market-data/{symbol} — live ticker snapshot for a subscribed symbol
    GET /api/search/{query}       — search IB symbol database (reqMatchingSymbols)
"""

import asyncio
import math
from fastapi import APIRouter, HTTPException, Request

from src.core.account import get_account_summary, get_positions
from src.api.schemas import (
    AccountSummaryResponse,
    PositionResponse,
    MarketDataResponse,
    SymbolSearchResult,
)

router = APIRouter(prefix="/api", tags=["account"])

_ACCOUNT_FIELDS = [
    "NetLiquidation",
    "TotalCashValue",
    "AvailableFunds",
    "BuyingPower",
    "GrossPositionValue",
    "MaintMarginReq",
    "UnrealizedPnL",
    "RealizedPnL",
]


def _safe_float(value) -> float | None:
    """Convert to float, returning None for nan / inf / unparseable values."""
    try:
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _check_ib(request: Request):
    ib = getattr(request.app.state, "ib", None)
    if ib is None or not ib.isConnected():
        raise HTTPException(status_code=503, detail="IB is not connected")
    return ib


# ─── Account summary ──────────────────────────────────────────────────────────

@router.get("/account", response_model=AccountSummaryResponse)
async def get_account(request: Request):
    """Return key account metrics from IB."""
    ib = _check_ib(request)
    raw = await get_account_summary(ib)
    return AccountSummaryResponse(
        account=ib.managedAccounts()[0],
        summary={k: _safe_float(raw.get(k)) for k in _ACCOUNT_FIELDS if k in raw},
    )


# ─── Positions ────────────────────────────────────────────────────────────────

@router.get("/positions", response_model=list[PositionResponse])
async def get_positions_endpoint(request: Request):
    """Return all current open positions."""
    ib = _check_ib(request)
    positions = await get_positions(ib)
    return [
        PositionResponse(
            symbol=p["symbol"],
            sec_type=p["sec_type"],
            exchange=p.get("exchange", ""),
            position=float(p["position"]),
            avg_cost=_safe_float(p["avg_cost"]),
        )
        for p in positions
    ]


# ─── Symbol search ────────────────────────────────────────────────────────────

@router.get("/search/{query}", response_model=list[SymbolSearchResult])
async def search_symbols(request: Request, query: str):
    """
    Search IB's symbol database using reqMatchingSymbols.
    Returns up to 16 matches (IB hard limit) filtered to equities / ETFs.
    """
    ib = _check_ib(request)
    if len(query.strip()) < 1:
        return []

    matches = await ib.reqMatchingSymbolsAsync(query.strip())
    if not matches:
        return []

    results: list[SymbolSearchResult] = []
    for desc in matches:
        c = desc.contract
        if c.currency != "USD" or c.secType not in ("STK",):
            continue
        results.append(SymbolSearchResult(
            symbol=c.symbol,
            name=c.description or "",
            sec_type=c.secType,
            exchange=c.primaryExchange or c.exchange or "",
        ))

    return results


# ─── Market data snapshot ─────────────────────────────────────────────────────

@router.get("/market-data/{symbol}", response_model=MarketDataResponse)
async def get_market_data(request: Request, symbol: str):
    """
    Return the latest tick snapshot for a symbol.
    If the symbol is not yet subscribed, dynamically subscribe and wait 2 s for
    initial data to arrive before responding.
    """
    sym = symbol.upper()
    ib = _check_ib(request)
    engine = request.app.state.engine
    ticker = engine.get_ticker(sym)

    if ticker is None:
        if engine._stream is None:
            from src.data.market_data import MarketDataStream
            engine._stream = MarketDataStream(ib)

        await engine.subscribe_symbol(sym)
        await asyncio.sleep(2)
        ticker = engine.get_ticker(sym)

    if ticker is None:
        raise HTTPException(
            status_code=503,
            detail=f"Could not obtain market data for '{sym}'. IB may have rejected the subscription.",
        )

    return MarketDataResponse(
        symbol=sym,
        bid=_safe_float(ticker.bid),
        ask=_safe_float(ticker.ask),
        last=_safe_float(ticker.last),
        volume=_safe_float(ticker.volume),
        close=_safe_float(ticker.close),
    )
