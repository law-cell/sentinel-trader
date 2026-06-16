"""
Action Executors
================
Two dispatch layers, called when a rule's condition is satisfied:

1. Channel dispatch (dispatch_channel) — HOW an alert is delivered:
    log       Write a structured log entry via loguru (INFO level)
    console   Print a highlighted alert to the terminal (with ANSI color)
    telegram  Send a Telegram message (requires TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env)
    notify    Alias for telegram (backward-compatible)

   Each channel handler has the signature:
       (rule_name: str, symbol: str, ticker: Ticker) -> None

2. Action dispatch (execute_rule_action) — WHAT happens on trigger, based on
   rule.action.type:
    "alert"                 Send an alert via the rule's channel.
    "propose_stock_order"   Build a StockOrderProposal, validate it, and
                            (if it passes) hand it to the proposal tracker
                            and dispatcher for user approval.
    "propose_option_order"  Same, but for an OptionOrderProposal — fetches
                            an option premium estimate first.

   If a proposal fails pre-trade validation, the user is notified via a
   degraded alert ("Rule X triggered but blocked: <reason>") instead of
   silently dropping the trigger.
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta
from ib_async import Ticker
from loguru import logger

from src.config.settings import PROPOSAL_EXPIRY_SECONDS
from src.orders.dispatcher import get_dispatcher
from src.orders.models import OptionOrderProposal, Proposal, StockOrderProposal
from src.orders.pricing import get_option_mid_price
from src.orders.tracker import get_tracker
from src.orders.validation import validate_for_proposal


# ─── ANSI color helpers ───────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_RED    = "\033[31m"


def _price_str(ticker: Ticker) -> str:
    price = ticker.last or ticker.close
    return f"${price:.2f}" if price and price > 0 else "N/A"


def _price_float(ticker: Ticker) -> float:
    return (ticker.last or ticker.close) or 0.0


def _vol_str(ticker: Ticker) -> str:
    vol = ticker.volume
    return f"{vol:,.0f}" if vol and vol > 0 else "N/A"


from src.notifications.telegram import get_telegram_app


def _fire_and_forget(coro) -> None:
    """Schedule a coroutine on the running loop, or run it if there is none."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        asyncio.run(coro)


# ─── Action implementations ───────────────────────────────────────────────────

def log_action(rule_name: str, symbol: str, ticker: Ticker) -> None:
    """Write a structured log entry via loguru."""
    logger.info(
        f"RULE TRIGGERED | rule='{rule_name}' symbol={symbol} "
        f"price={_price_str(ticker)} volume={_vol_str(ticker)}"
    )


def console_action(rule_name: str, symbol: str, ticker: Ticker) -> None:
    """Print a color-highlighted alert directly to the terminal."""
    price = _price_str(ticker)
    vol   = _vol_str(ticker)
    line  = (
        f"{_BOLD}{_YELLOW}>>> ALERT{_RESET}  "
        f"{_BOLD}{_CYAN}{symbol}{_RESET}  "
        f"rule={_GREEN}{rule_name}{_RESET}  "
        f"price={_BOLD}{price}{_RESET}  "
        f"vol={vol}"
    )
    print(line, flush=True)


def telegram_action(rule_name: str, symbol: str, ticker: Ticker) -> None:
    """
    Send a Telegram alert for a triggered rule.

    Scheduled as a fire-and-forget asyncio Task so it never blocks
    the rule engine tick handler.
    """
    tg = get_telegram_app()
    if tg is None:
        return

    price = _price_float(ticker)
    condition_desc = f"price = {_price_str(ticker)}"
    _fire_and_forget(tg.send_alert(rule_name, symbol, condition_desc, price))


# notify is kept as an alias so existing rules.json entries still work
def notify_action(rule_name: str, symbol: str, ticker: Ticker) -> None:
    telegram_action(rule_name, symbol, ticker)


# ─── Channel dispatch ─────────────────────────────────────────────────────────
# Delivery channels for alerts — how a notification reaches the user.

_CHANNELS = {
    "log":      log_action,
    "console":  console_action,
    "telegram": telegram_action,
    "notify":   notify_action,
}


def dispatch_channel(channel_name: str, rule_name: str, symbol: str, ticker: Ticker) -> None:
    """
    Dispatch to the named delivery channel handler.

    Falls back to log_action if the channel name is unrecognised.
    """
    handler = _CHANNELS.get(channel_name)
    if handler is None:
        logger.warning(f"Unknown channel '{channel_name}' for rule '{rule_name}' — falling back to log")
        handler = log_action
    try:
        handler(rule_name, symbol, ticker)
    except Exception as e:
        logger.error(f"Channel '{channel_name}' failed for rule '{rule_name}': {e}")


def dispatch_degraded_alert(channel_name: str, rule_name: str, symbol: str, ticker: Ticker, reason: str) -> None:
    """
    Notify the user that a rule fired but its order proposal was blocked by
    pre-trade validation. Always logged (regardless of channel) since this is
    a safety-relevant event; additionally sent over the rule's channel when
    that channel supports a custom message (console, telegram/notify).
    """
    message = f"Rule '{rule_name}' triggered but blocked: {reason}"
    logger.warning(message)

    if channel_name == "console":
        line = f"{_BOLD}{_RED}>>> BLOCKED{_RESET}  {_BOLD}{_CYAN}{symbol}{_RESET}  {message}"
        print(line, flush=True)
    elif channel_name in ("telegram", "notify"):
        tg = get_telegram_app()
        if tg is None:
            return
        price = _price_float(ticker)
        _fire_and_forget(tg.send_alert(rule_name, symbol, f"⚠️ Blocked: {reason}", price))


# ─── Action dispatch ──────────────────────────────────────────────────────────
# What happens when a rule's condition fires. "alert" sends a notification via
# the rule's channel. Order-proposal actions build a Proposal, run pre-trade
# validation, and either hand it off for approval or send a degraded alert.

async def _handle_alert(rule, symbol: str, ticker: Ticker, ib=None) -> Proposal | None:
    dispatch_channel(rule.channel, rule.name, symbol, ticker)
    return None


async def _handle_stock_order_proposal(rule, symbol: str, ticker: Ticker, ib=None) -> Proposal | None:
    action = rule.action  # StockOrderAction
    price = _price_float(ticker)
    notional = action.quantity * (action.limit_price if action.limit_price is not None else price)

    now = datetime.now()
    proposal = StockOrderProposal(
        id=str(uuid.uuid4()),
        rule_id=rule.name,
        rule_name=rule.name,
        symbol=symbol,
        created_at=now,
        expires_at=now + timedelta(seconds=PROPOSAL_EXPIRY_SECONDS),
        status="PENDING",
        estimated_notional_usd=notional,
        trigger_price=price,
        side=action.side,
        quantity=action.quantity,
        order_type=action.order_type,
        limit_price=action.limit_price,
    )

    tracker = get_tracker()
    result = validate_for_proposal(proposal, tracker, ib)
    if not result.ok:
        dispatch_degraded_alert(rule.channel, rule.name, symbol, ticker, result.reason)
        return None

    tracker.create(proposal)
    await get_dispatcher().dispatch(proposal)
    return proposal


async def _handle_option_order_proposal(rule, symbol: str, ticker: Ticker, ib=None) -> Proposal | None:
    action = rule.action  # OptionOrderAction
    price = _price_float(ticker)
    expiry_date = date.today() + timedelta(days=action.expiry_days)

    premium = await get_option_mid_price(symbol, action.right, action.strike, expiry_date)
    notional = action.quantity * premium * 100

    now = datetime.now()
    proposal = OptionOrderProposal(
        id=str(uuid.uuid4()),
        rule_id=rule.name,
        rule_name=rule.name,
        symbol=symbol,
        created_at=now,
        expires_at=now + timedelta(seconds=PROPOSAL_EXPIRY_SECONDS),
        status="PENDING",
        estimated_notional_usd=notional,
        trigger_price=price,
        right=action.right,
        strike=action.strike,
        expiry_date=expiry_date,
        quantity=action.quantity,
    )

    tracker = get_tracker()
    result = validate_for_proposal(proposal, tracker, ib)
    if not result.ok:
        dispatch_degraded_alert(rule.channel, rule.name, symbol, ticker, result.reason)
        return None

    tracker.create(proposal)
    await get_dispatcher().dispatch(proposal)
    return proposal


_ACTION_HANDLERS = {
    "alert":                _handle_alert,
    "propose_stock_order":  _handle_stock_order_proposal,
    "propose_option_order": _handle_option_order_proposal,
}


async def execute_rule_action(rule, symbol: str, ticker: Ticker, ib=None) -> Proposal | None:
    """
    Dispatch on rule.action.type. Returns the created Proposal for
    propose_*_order actions that passed validation, otherwise None
    (alert actions, or proposals blocked by validation).

    Logs an error (without raising) if the action type is unrecognised —
    should be unreachable since `Action` is a discriminated union, but
    guards against future schema additions.
    """
    handler = _ACTION_HANDLERS.get(rule.action.type)
    if handler is None:
        logger.error(f"Unknown action type '{rule.action.type}' for rule '{rule.name}' — no action taken")
        return None
    return await handler(rule, symbol, ticker, ib)
