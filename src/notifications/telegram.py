"""
Telegram Notifier
=================
Sends trading alerts to a Telegram chat via python-telegram-bot (long-polling
Application — no public URL required).

Setup:
    1. Create a bot via @BotFather and copy the token
    2. Get your chat_id (send a message to the bot, then call
       https://api.telegram.org/bot<TOKEN>/getUpdates)
    3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env

Usage:
    app = TelegramApplication(token="...", chat_id="...")
    await app.start()
    await app.send_alert("NVDA Alert", "NVDA", "price > 150", 180.05)
    await app.stop()
"""

from datetime import datetime
from loguru import logger
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes


class TelegramApplication:
    """Wraps a python-telegram-bot Application running in long-polling mode."""

    def __init__(self, token: str, chat_id: str):
        self.chat_id = str(chat_id)
        self.app = Application.builder().token(token).build()
        self._ib = None

    async def start(self, ib=None) -> None:
        """Initialize, start, and begin long-polling. Call once on app startup."""
        self._ib = ib
        await self.app.initialize()
        await self.app.start()
        self.app.add_handler(CallbackQueryHandler(self._on_proposal_callback))
        await self.app.updater.start_polling()
        logger.info("Telegram polling started")

    async def _on_proposal_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button taps for proposal approve/reject."""
        query = update.callback_query
        data = query.data or ""
        parts = data.split(":")

        if len(parts) != 3 or parts[0] != "proposal" or parts[2] not in ("approve", "reject"):
            await query.answer()
            return

        proposal_id = parts[1]
        action = parts[2]

        if self._ib is None:
            await query.answer("IB not connected", show_alert=True)
            return

        from src.orders.service import approve_proposal, reject_proposal
        if action == "approve":
            result = await approve_proposal(proposal_id, self._ib)
        else:
            result = await reject_proposal(proposal_id)

        if not result.ok:
            await query.answer(result.reason, show_alert=True)
        else:
            await query.answer()

    async def stop(self) -> None:
        """Stop polling and shut down cleanly. Call once on app shutdown.

        All three calls are required in this order — skipping any leaves
        polling tasks half-alive, and Telegram rejects the next getUpdates
        with "another instance is already polling" until it times out.
        """
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        logger.info("Telegram polling stopped")

    async def send_message(self, text: str) -> bool:
        """
        Send an HTML-formatted message to the configured chat.

        Returns True on success, False on failure (never raises).
        """
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return True
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


# ─── Lazy singleton ────────────────────────────────────────────────────────
# Mirrors get_tracker()/get_dispatcher() so rule actions (which run outside
# any Request context) can reach the shared TelegramApplication instance.

_telegram_app: TelegramApplication | None = None
_telegram_app_checked = False


def get_telegram_app() -> TelegramApplication | None:
    global _telegram_app, _telegram_app_checked
    if _telegram_app_checked:
        return _telegram_app
    _telegram_app_checked = True

    from src.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _telegram_app = TelegramApplication(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        logger.info("Telegram application initialised")
    else:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env to enable Telegram alerts"
        )
    return _telegram_app
