"""
Telegram Proposal Dispatcher
=============================
Sends order proposals to Telegram as messages with inline approve/reject
buttons. Edits the same message in place when the proposal reaches a
terminal state (executed, rejected, expired, failed).
"""

import itertools
from datetime import datetime
from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.orders.models import OptionOrderProposal, Proposal, StockOrderProposal

_mock_order_ids = itertools.count(900001)


def _order_line(proposal: Proposal) -> str:
    if isinstance(proposal, StockOrderProposal):
        line = f"{proposal.side} {proposal.quantity} {proposal.symbol} {proposal.order_type}"
        if proposal.order_type == "LIMIT" and proposal.limit_price is not None:
            line += f" @ ${proposal.limit_price:.2f}"
        return line
    if isinstance(proposal, OptionOrderProposal):
        return (
            f"SELL {proposal.quantity} {proposal.symbol} "
            f"{proposal.expiry_date.isoformat()} {proposal.strike:g}{proposal.right}"
        )
    return "unknown"


def _expiry_str(expires_at: datetime) -> str:
    minutes_left = max(0, int((expires_at - datetime.now()).total_seconds() / 60))
    return f"{expires_at.strftime('%H:%M')} (in {minutes_left} min)"


def _format_pending(proposal: Proposal) -> str:
    return (
        f"📋 <b>Order Proposal — <code>{proposal.symbol}</code></b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Rule:</b> {proposal.rule_name}\n"
        f"📦 {_order_line(proposal)}\n"
        f"💰 <b>Est. Notional:</b> ${proposal.estimated_notional_usd:,.2f}\n"
        f"📍 <b>Trigger:</b> ${proposal.trigger_price:.2f}\n"
        f"⏰ <b>Expires:</b> {_expiry_str(proposal.expires_at)}"
    )


def _format_executed(proposal: Proposal) -> str:
    return (
        f"✅ <b>Order Executed — <code>{proposal.symbol}</code></b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Rule:</b> {proposal.rule_name}\n"
        f"📦 {_order_line(proposal)}\n"
        f"💰 <b>Est. Notional:</b> ${proposal.estimated_notional_usd:,.2f}\n"
        f"🔖 <b>IB Order:</b> {proposal.ib_order_id}"
    )


def _format_rejected(proposal: Proposal) -> str:
    return (
        f"❌ <b>Order Rejected — <code>{proposal.symbol}</code></b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Rule:</b> {proposal.rule_name}\n"
        f"📦 {_order_line(proposal)}"
    )


def _format_expired(proposal: Proposal) -> str:
    return (
        f"⏰ <b>Order Expired — <code>{proposal.symbol}</code></b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Rule:</b> {proposal.rule_name}\n"
        f"📦 {_order_line(proposal)}"
    )


def _format_failed(proposal: Proposal) -> str:
    return (
        f"⚠️ <b>Execution Failed — <code>{proposal.symbol}</code></b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Rule:</b> {proposal.rule_name}\n"
        f"📦 {_order_line(proposal)}\n"
        f"❌ <b>Reason:</b> {proposal.failure_reason or 'unknown'}"
    )


_STATUS_FORMATTERS = {
    "EXECUTED": _format_executed,
    "REJECTED": _format_rejected,
    "EXPIRED":  _format_expired,
    "FAILED":   _format_failed,
}


class TelegramProposalDispatcher:
    """Sends proposals as Telegram messages with inline buttons; edits on status changes."""

    def __init__(self, bot, chat_id: str) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def dispatch(self, proposal: Proposal) -> None:
        text = _format_pending(proposal)
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"proposal:{proposal.id}:approve"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"proposal:{proposal.id}:reject"),
        ]])
        try:
            msg = await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            proposal.telegram_message_id = msg.message_id
            logger.info(f"Telegram proposal sent: {proposal.id} message_id={msg.message_id}")
        except Exception as e:
            logger.error(f"Telegram dispatch failed for proposal {proposal.id}: {e}")

    async def dispatch_execution(self, proposal: Proposal) -> int:
        """Stub: log what WOULD be executed. Returns a mock ib_order_id."""
        mock_order_id = next(_mock_order_ids)
        logger.info(
            f"WOULD EXECUTE order for proposal {proposal.id} "
            f"(mock ib_order_id={mock_order_id})"
        )
        return mock_order_id

    async def edit_message(self, proposal: Proposal) -> None:
        """Edit the proposal's Telegram message to reflect its terminal status."""
        if proposal is None or proposal.telegram_message_id is None:
            return
        formatter = _STATUS_FORMATTERS.get(proposal.status)
        if formatter is None:
            return
        text = formatter(proposal)
        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=proposal.telegram_message_id,
                text=text,
                parse_mode="HTML",
            )
            logger.info(
                f"Telegram message edited: proposal {proposal.id} status={proposal.status}"
            )
        except Exception as e:
            logger.warning(f"Telegram edit_message failed for proposal {proposal.id}: {e}")
