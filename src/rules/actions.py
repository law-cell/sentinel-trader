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
   rule.action.type ("alert", "propose_stock_order", "propose_option_order").
   "alert" delegates to the rule's channel. Order-proposal types are stubs
   until order execution lands.
"""

import asyncio
from ib_async import Ticker
from loguru import logger


# ─── ANSI color helpers ───────────────────────────────────────────────────────

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"


def _price_str(ticker: Ticker) -> str:
    price = ticker.last or ticker.close
    return f"${price:.2f}" if price and price > 0 else "N/A"


def _price_float(ticker: Ticker) -> float:
    return (ticker.last or ticker.close) or 0.0


def _vol_str(ticker: Ticker) -> str:
    vol = ticker.volume
    return f"{vol:,.0f}" if vol and vol > 0 else "N/A"


# ─── Lazy Telegram notifier singleton ────────────────────────────────────────
# Initialised on first use; None if env vars are not set.

_notifier = None
_notifier_checked = False


def _get_notifier():
    global _notifier, _notifier_checked
    if _notifier_checked:
        return _notifier
    _notifier_checked = True

    from src.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        from src.notifications.telegram import TelegramNotifier
        _notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        logger.info("Telegram notifier initialised")
    else:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env to enable Telegram alerts"
        )
    return _notifier


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

    The HTTP request is fire-and-forget: it is scheduled as an asyncio Task
    on the running event loop so it never blocks the rule engine tick handler.
    """
    notifier = _get_notifier()
    if notifier is None:
        return

    price = _price_float(ticker)
    condition_desc = f"price = {_price_str(ticker)}"

    coro = notifier.send_alert(rule_name, symbol, condition_desc, price)

    try:
        # We're inside the ib_async event loop — schedule without awaiting
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop (e.g. called from a test outside async context)
        asyncio.run(coro)


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


# ─── Action dispatch ──────────────────────────────────────────────────────────
# What happens when a rule's condition fires. "alert" sends a notification via
# the rule's channel. Order-proposal actions are stubs until execution lands
# (see Sunday scope) — they currently just alert via the channel.

def _handle_alert(rule, symbol: str, ticker: Ticker) -> None:
    dispatch_channel(rule.channel, rule.name, symbol, ticker)


def _handle_stock_order_stub(rule, symbol: str, ticker: Ticker) -> None:
    logger.warning(
        f"Rule '{rule.name}' triggered a propose_stock_order action — "
        "order proposals are not yet implemented; sending alert instead"
    )
    dispatch_channel(rule.channel, rule.name, symbol, ticker)


def _handle_option_order_stub(rule, symbol: str, ticker: Ticker) -> None:
    logger.warning(
        f"Rule '{rule.name}' triggered a propose_option_order action — "
        "order proposals are not yet implemented; sending alert instead"
    )
    dispatch_channel(rule.channel, rule.name, symbol, ticker)


_ACTION_HANDLERS = {
    "alert":                 _handle_alert,
    "propose_stock_order":   _handle_stock_order_stub,
    "propose_option_order":  _handle_option_order_stub,
}


def execute_rule_action(rule, symbol: str, ticker: Ticker) -> None:
    """
    Dispatch on rule.action.type. Falls back to alert behaviour if the
    action type is unrecognised.
    """
    handler = _ACTION_HANDLERS.get(rule.action.type, _handle_alert)
    handler(rule, symbol, ticker)
