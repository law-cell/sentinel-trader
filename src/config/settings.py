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
