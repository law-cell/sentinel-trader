"""
Proposal Service
================
Shared approve/reject logic called by both HTTP routes and the Telegram
callback handler. Keeping it here avoids duplicating the state-machine
flow (tracker transitions → validation → dispatch_execution → edit) in
two places.
"""

from dataclasses import dataclass
from typing import Optional

from src.orders.dispatcher import get_dispatcher
from src.orders.models import Proposal
from src.orders.tracker import get_tracker
from src.orders.validation import validate_for_execution


@dataclass
class ApprovalResult:
    ok: bool
    proposal: Optional[Proposal]
    reason: str = ""


async def approve_proposal(proposal_id: str, ib=None) -> ApprovalResult:
    tracker = get_tracker()
    proposal = tracker.get(proposal_id)
    if proposal is None:
        return ApprovalResult(ok=False, proposal=None, reason=f"Proposal '{proposal_id}' not found")

    ok, reason = tracker.approve(proposal_id)
    if not ok:
        return ApprovalResult(ok=False, proposal=proposal, reason=reason)

    result = validate_for_execution(proposal, tracker, ib)
    if not result.ok:
        tracker.mark_failed(proposal_id, result.reason)
        failed = tracker.get(proposal_id)
        await get_dispatcher().edit_message(failed)
        return ApprovalResult(ok=False, proposal=failed, reason=result.reason)

    dispatcher = get_dispatcher()
    ib_order_id = await dispatcher.dispatch_execution(proposal)
    tracker.mark_executed(proposal_id, ib_order_id)
    final = tracker.get(proposal_id)
    await dispatcher.edit_message(final)
    return ApprovalResult(ok=True, proposal=final)


async def reject_proposal(proposal_id: str) -> ApprovalResult:
    tracker = get_tracker()
    proposal = tracker.get(proposal_id)
    if proposal is None:
        return ApprovalResult(ok=False, proposal=None, reason=f"Proposal '{proposal_id}' not found")

    ok, reason = tracker.reject(proposal_id)
    if not ok:
        return ApprovalResult(ok=False, proposal=proposal, reason=reason)

    final = tracker.get(proposal_id)
    await get_dispatcher().edit_message(final)
    return ApprovalResult(ok=True, proposal=final)
