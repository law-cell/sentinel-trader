"""
Condition Evaluators
====================
Each evaluator receives an ib_async Ticker object and a condition dict,
and returns True if the condition is met.

Supported condition types:
    price_above       last > threshold
    price_below       last < threshold
    price_change_pct  abs % change from prev close > threshold
    volume_above      volume > threshold

Condition dict format examples:
    {"type": "price_above",      "threshold": 150.0}
    {"type": "price_below",      "threshold": 100.0}
    {"type": "price_change_pct", "threshold": 2.0}   # 2% from prev close
    {"type": "volume_above",     "threshold": 5000000}
"""

from typing import Callable
from ib_async import Ticker
from loguru import logger


# ─── Individual evaluators ───────────────────────────────────────────────────

def _price_above(ticker: Ticker, params: dict) -> bool:
    price = ticker.last or ticker.close
    if not price or price <= 0:
        return False
    return price > params["threshold"]


def _price_below(ticker: Ticker, params: dict) -> bool:
    price = ticker.last or ticker.close
    if not price or price <= 0:
        return False
    return price < params["threshold"]


def _price_change_pct(ticker: Ticker, params: dict) -> bool:
    """
    Checks if the absolute percentage change from the previous close exceeds
    the given threshold.  Uses ticker.close as the baseline (IB provides
    yesterday's closing price in that field).
    """
    price = ticker.last or ticker.ask
    baseline = ticker.close
    if not price or not baseline or price <= 0 or baseline <= 0:
        return False
    pct_change = abs((price - baseline) / baseline * 100)
    return pct_change > params["threshold"]


def _volume_above(ticker: Ticker, params: dict) -> bool:
    vol = ticker.volume
    if vol is None or vol <= 0:
        return False
    return vol > params["threshold"]


# ─── Dispatch table ───────────────────────────────────────────────────────────

_EVALUATORS: dict[str, Callable[[Ticker, dict], bool]] = {
    "price_above": _price_above,
    "price_below": _price_below,
    "price_change_pct": _price_change_pct,
    "volume_above": _volume_above,
}


# ─── Public API ───────────────────────────────────────────────────────────────

def evaluate_condition(ticker: Ticker, condition: dict) -> bool:
    """
    Evaluate a condition dict against a live Ticker.

    Args:
        ticker:    ib_async Ticker with latest market data
        condition: dict with at least a "type" key

    Returns:
        True if the condition is satisfied, False otherwise.
        Returns False (not raise) if condition type is unknown or data missing.
    """
    ctype = condition.get("type")
    evaluator = _EVALUATORS.get(ctype)
    if evaluator is None:
        logger.warning(f"Unknown condition type: '{ctype}' — skipping")
        return False

    try:
        return evaluator(ticker, condition)
    except KeyError as e:
        logger.warning(f"Condition '{ctype}' missing required param {e} — skipping")
        return False
    except Exception as e:
        logger.error(f"Error evaluating condition '{ctype}': {e}")
        return False
