"""
Proposal Tracker
================
In-memory store for order proposals and their status transitions.

Container restart loses pending proposals — that's intentional: a
restart implicitly cancels any in-flight approvals rather than risking
a stale proposal being approved against a now-different world state.

The tracker is a SINGLETON — use get_tracker() everywhere (rule engine,
FastAPI routes via Depends).
"""

from datetime import date, datetime
from loguru import logger

from src.orders.models import Proposal

# Valid status transitions. Anything not listed here is rejected.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "PENDING":  {"APPROVED", "REJECTED", "EXPIRED"},
    "APPROVED": {"EXECUTED", "FAILED"},
    "REJECTED": set(),
    "EXPIRED":  set(),
    "EXECUTED": set(),
    "FAILED":   set(),
}


class ProposalTracker:
    def __init__(self) -> None:
        self._proposals: dict[str, Proposal] = {}
        self._daily_executed: dict[date, int] = {}

    # ─── Create / read ──────────────────────────────────────────────────────

    def create(self, proposal: Proposal) -> None:
        self._proposals[proposal.id] = proposal
        logger.info(
            f"Proposal created: {proposal.id} "
            f"({proposal.kind}, {proposal.symbol}, rule='{proposal.rule_name}')"
        )

    def get(self, proposal_id: str) -> Proposal | None:
        return self._proposals.get(proposal_id)

    def list_pending(self) -> list[Proposal]:
        return [p for p in self._proposals.values() if p.status == "PENDING"]

    def list_history(self, limit: int = 20) -> list[Proposal]:
        """All proposals regardless of status, newest first."""
        return sorted(self._proposals.values(), key=lambda p: p.created_at, reverse=True)[:limit]

    # ─── Status transitions ─────────────────────────────────────────────────

    def _transition(self, proposal_id: str, new_status: str) -> tuple[bool, str]:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return False, f"Proposal '{proposal_id}' not found"

        current = proposal.status
        if new_status not in _VALID_TRANSITIONS.get(current, set()):
            msg = f"Invalid transition: {current} -> {new_status}"
            logger.warning(msg)
            return False, msg

        proposal.status = new_status
        return True, "ok"

    def approve(self, proposal_id: str) -> tuple[bool, str]:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return False, f"Proposal '{proposal_id}' not found"
        if proposal.status == "EXPIRED":
            msg = "Cannot approve expired proposal"
            logger.warning(msg)
            return False, msg
        return self._transition(proposal_id, "APPROVED")

    def reject(self, proposal_id: str) -> tuple[bool, str]:
        return self._transition(proposal_id, "REJECTED")

    def mark_executed(self, proposal_id: str, ib_order_id: int) -> None:
        ok, msg = self._transition(proposal_id, "EXECUTED")
        if not ok:
            logger.warning(f"mark_executed({proposal_id}) failed: {msg}")
            return
        proposal = self._proposals[proposal_id]
        proposal.ib_order_id = ib_order_id
        today = datetime.now().date()
        self._daily_executed[today] = self._daily_executed.get(today, 0) + 1

    def mark_failed(self, proposal_id: str, reason: str) -> None:
        ok, msg = self._transition(proposal_id, "FAILED")
        if not ok:
            logger.warning(f"mark_failed({proposal_id}) failed: {msg}")
            return
        self._proposals[proposal_id].failure_reason = reason

    def expire_stale(self) -> int:
        """Move any PENDING proposal past its expires_at to EXPIRED. Returns count expired."""
        now = datetime.now()
        count = 0
        for proposal in self._proposals.values():
            if proposal.status == "PENDING" and proposal.expires_at <= now:
                proposal.status = "EXPIRED"
                count += 1
        if count:
            logger.info(f"Expired {count} stale proposal(s)")
        return count

    # ─── Limits / duplicate checks ──────────────────────────────────────────

    def daily_executed_count(self, d: date | None = None) -> int:
        d = d or datetime.now().date()
        return self._daily_executed.get(d, 0)

    def has_active_duplicate(self, symbol: str, kind: str, exclude_id: str | None = None) -> bool:
        """
        True if a PENDING or APPROVED proposal already exists for this symbol+kind.

        `exclude_id` excludes a specific proposal from the check — needed when
        re-validating a proposal that is itself already PENDING/APPROVED in the
        tracker (Pass 2, validate_for_execution), so it doesn't count as its
        own duplicate.
        """
        return any(
            p.id != exclude_id and p.symbol == symbol and p.kind == kind
            and p.status in ("PENDING", "APPROVED")
            for p in self._proposals.values()
        )


_tracker: ProposalTracker | None = None


def get_tracker() -> ProposalTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProposalTracker()
    return _tracker
