"""
Proposal Dispatcher
===================
Delivers order proposals to the user for approval, and "executes"
approved proposals.

StubProposalDispatcher just logs — Sunday afternoon swaps this for
TelegramProposalDispatcher with real inline approve/reject buttons and
real ib.placeOrder.
"""

import itertools
from loguru import logger

from src.orders.models import OptionOrderProposal, Proposal, StockOrderProposal

# Mock IB order IDs for stub execution — real IDs come from ib.placeOrder() (Sunday afternoon).
_mock_order_ids = itertools.count(900001)


def format_proposal_for_log(proposal: Proposal) -> str:
    if isinstance(proposal, StockOrderProposal):
        order_desc = f"{proposal.side} {proposal.quantity} {proposal.symbol} {proposal.order_type}"
        if proposal.order_type == "LIMIT" and proposal.limit_price is not None:
            order_desc += f" @ ${proposal.limit_price:.2f}"
    elif isinstance(proposal, OptionOrderProposal):
        order_desc = (
            f"SELL {proposal.quantity} {proposal.symbol} "
            f"{proposal.expiry_date.isoformat()} {proposal.strike:g}{proposal.right}"
        )
    else:
        order_desc = "unknown proposal kind"

    return (
        f"{order_desc} | rule='{proposal.rule_name}' "
        f"trigger_price=${proposal.trigger_price:.2f} "
        f"est_notional=${proposal.estimated_notional_usd:,.2f} "
        f"id={proposal.id}"
    )


class StubProposalDispatcher:
    """Logs what WOULD happen instead of sending to Telegram / calling placeOrder."""

    async def dispatch(self, proposal: Proposal) -> None:
        logger.info(f"WOULD DISPATCH proposal {proposal.id}: {format_proposal_for_log(proposal)}")

    async def dispatch_execution(self, proposal: Proposal) -> int:
        """Pretend to place the order. Returns a mock ib_order_id."""
        mock_order_id = next(_mock_order_ids)
        logger.info(
            f"WOULD EXECUTE order for proposal {proposal.id} "
            f"(mock ib_order_id={mock_order_id}): {format_proposal_for_log(proposal)}"
        )
        return mock_order_id


_dispatcher: StubProposalDispatcher | None = None


def get_dispatcher() -> StubProposalDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = StubProposalDispatcher()
    return _dispatcher
