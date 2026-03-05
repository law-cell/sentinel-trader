"""
Telegram Integration Test
=========================
Sends a real test message to verify bot token and chat_id are correct.

Usage:
    python tests/test_telegram.py

Make sure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in .env first.
"""

import asyncio
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from src.notifications.telegram import TelegramNotifier


async def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are not set in .env\n"
            "Edit .env and fill in both values, then re-run this script."
        )
        sys.exit(1)

    logger.info(f"Using chat_id: {TELEGRAM_CHAT_ID}")
    logger.info(f"Using token: {TELEGRAM_BOT_TOKEN[:10]}...")

    notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    # 1. Plain message
    logger.info("Sending plain test message...")
    ok = await notifier.send_message("✅ IB Trading Assistant — Telegram connection test successful!")
    if not ok:
        logger.error("Plain message failed. Check token and chat_id.")
        sys.exit(1)
    logger.success("Plain message sent OK")

    # 2. Formatted alert (simulates a real rule trigger)
    logger.info("Sending formatted alert...")
    ok = await notifier.send_alert(
        rule_name="NVDA Price Alert - Breakout Above 150",
        symbol="NVDA",
        condition="price > 150.0",
        current_value=180.05,
    )
    if not ok:
        logger.error("Alert message failed.")
        sys.exit(1)
    logger.success("Alert message sent OK")

    logger.success("All Telegram tests passed! Check your Telegram chat.")


if __name__ == "__main__":
    asyncio.run(main())
