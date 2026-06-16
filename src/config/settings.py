"""
Centralized configuration loaded from .env file.
Copy .env.example to .env and adjust values before running.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# IB Connection
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7497"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))

# Watchlist
WATCHLIST = [s.strip() for s in os.getenv("WATCHLIST", "NVDA,TSLA,AAPL,SPY,QQQ").split(",")]

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Telegram Notifications (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Anthropic API (natural-language rule creation)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ──────────────────────────────────────────────────────────
# TRADING SAFETY CONFIG — CHANGES REQUIRE REBUILD + REDEPLOY
# ──────────────────────────────────────────────────────────
# To enable live trading:
#   1. Change TRADING_MODE to "live" below
#   2. Review ALLOWED_SYMBOLS — current list is biased toward
#      paper-friendly liquid names
#   3. Rebuild docker image: docker compose build --no-cache
#   4. Redeploy
# Every step is intentional friction. Live mode is NOT toggleable
# via .env or UI by design.
#
# Note: this is distinct from the TRADING_MODE in .env, which only
# controls which IB account the Gateway container logs into
# (paper/live). This setting gates whether SentinelTrader itself is
# allowed to execute proposed orders.

TRADING_MODE = "paper"  # ← HARDCODED

ALLOWED_SYMBOLS = {
    "AAPL", "NVDA", "TSLA", "META", "MSFT", "GOOGL",
    "APP", "RKLB", "LITE", "CRDO",
}

MAX_NOTIONAL_PER_ORDER_USD = 2000.0
MAX_EXECUTED_ORDERS_PER_DAY = 5    # Counts EXECUTED, not proposed
PROPOSAL_EXPIRY_SECONDS = 180      # 3 minutes

# Options-specific safety
MAX_OPTION_PREMIUM_USD = 5.0       # per contract
MAX_OPTION_EXPIRY_DAYS = 60
OPTION_SIDE_ALLOWED = {"SELL"}     # sell-to-open only (no long options)
OPTION_ORDER_TYPE_FORCED = "LIMIT"  # market orders on options are unsafe


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Test-trigger endpoint (POST /api/rules/{rule_id}/trigger-test) lets QA
# pretend a rule's condition just fired, without waiting for real market
# conditions. Defaults to disabled: an unset/empty env var in production
# means the endpoint doesn't exist. Set ENABLE_TEST_TRIGGER=true in .env
# for dev/local.
ENABLE_TEST_TRIGGER = _truthy(os.getenv("ENABLE_TEST_TRIGGER", "false"))
