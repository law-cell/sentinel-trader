"""
Telegram Notifier
=================
Sends trading alerts to a Telegram chat via Bot API using httpx (async).

Setup:
    1. Create a bot via @BotFather and copy the token
    2. Get your chat_id (send a message to the bot, then call
       https://api.telegram.org/bot<TOKEN>/getUpdates)
    3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env

Usage:
    notifier = TelegramNotifier(token="...", chat_id="...")
    await notifier.send_message("Hello from SentinelTrader!")
    await notifier.send_alert("NVDA Alert", "NVDA", "price > 150", 180.05)
"""

from datetime import datetime
import httpx
from loguru import logger


_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Async Telegram notification client (no external bot library required)."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self._url = _API_BASE.format(token=token)

    async def send_message(self, text: str) -> bool:
        """
        Send a plain or HTML-formatted message to the configured chat.

        Returns True on success, False on failure (never raises).
        """
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._url, json=payload)
                data = resp.json()
                if data.get("ok"):
                    return True
                logger.error(f"Telegram API error: {data.get('description', data)}")
                return False
        except httpx.TimeoutException:
            logger.error("Telegram send timed out")
            return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def send_alert(
        self,
        rule_name: str,
        symbol: str,
        condition: str,
        current_value: float,
    ) -> bool:
        """
        Send a formatted trading alert message.

        Args:
            rule_name:     Display name of the triggered rule
            symbol:        Ticker symbol (e.g. "NVDA")
            condition:     Human-readable condition description (e.g. "price > 150")
            current_value: The current price or metric that triggered the rule
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            "🚨 <b>Trading Alert</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Rule:</b> {rule_name}\n"
            f"📈 <b>Symbol:</b> <code>{symbol}</code>\n"
            f"⚡ <b>Condition:</b> {condition}\n"
            f"💰 <b>Current value:</b> <b>${current_value:.2f}</b>\n"
            f"🕐 <b>Time:</b> {now}"
        )
        success = await self.send_message(text)
        if success:
            logger.info(f"Telegram alert sent: rule='{rule_name}' symbol={symbol}")
        return success
