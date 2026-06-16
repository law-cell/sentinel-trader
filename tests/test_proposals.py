"""
Unit tests for OrderProposal models and ProposalTracker.

Run: pytest tests/test_proposals.py -v
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from src.orders.models import StockOrderProposal, OptionOrderProposal
from src.orders.tracker import ProposalTracker


def make_stock_proposal(
    symbol: str = "TSLA",
    status: str = "PENDING",
    expires_in: timedelta = timedelta(minutes=3),
    created_at: datetime | None = None,
) -> StockOrderProposal:
    now = created_at or datetime.now()
    return StockOrderProposal(
        id=str(uuid.uuid4()),
        rule_id="Buy 10 TSLA when it drops below $250",
        rule_name="Buy 10 TSLA when it drops below $250",
        symbol=symbol,
        created_at=now,
        expires_at=now + expires_in,
        status=status,
        estimated_notional_usd=2490.0,
        trigger_price=249.0,
        side="BUY",
        quantity=10,
        order_type="MARKET",
    )


def make_option_proposal(
    symbol: str = "NVDA",
    status: str = "PENDING",
    expires_in: timedelta = timedelta(minutes=3),
) -> OptionOrderProposal:
    now = datetime.now()
    return OptionOrderProposal(
        id=str(uuid.uuid4()),
        rule_id="NVDA covered call at $220",
        rule_name="NVDA covered call at $220",
        symbol=symbol,
        created_at=now,
        expires_at=now + expires_in,
        status=status,
        estimated_notional_usd=250.0,
        trigger_price=220.0,
        right="C",
        strike=240.0,
        expiry_date=date.today() + timedelta(days=30),
        quantity=1,
    )


# ─── Create + retrieve ──────────────────────────────────────────────────────

def test_create_and_retrieve():
    tracker = ProposalTracker()
    proposal = make_stock_proposal()

    tracker.create(proposal)

    retrieved = tracker.get(proposal.id)
    assert retrieved is not None
    assert retrieved.id == proposal.id
    assert retrieved.symbol == "TSLA"
    assert tracker.get("does-not-exist") is None


# ─── Status transitions ─────────────────────────────────────────────────────

def test_valid_transition_pending_to_approved_to_executed():
    tracker = ProposalTracker()
    proposal = make_stock_proposal()
    tracker.create(proposal)

    ok, reason = tracker.approve(proposal.id)
    assert ok is True
    assert tracker.get(proposal.id).status == "APPROVED"

    tracker.mark_executed(proposal.id, ib_order_id=12345)
    updated = tracker.get(proposal.id)
    assert updated.status == "EXECUTED"
    assert updated.ib_order_id == 12345


def test_valid_transition_pending_to_approved_to_failed():
    tracker = ProposalTracker()
    proposal = make_stock_proposal()
    tracker.create(proposal)

    tracker.approve(proposal.id)
    tracker.mark_failed(proposal.id, "IB rejected order: insufficient margin")

    updated = tracker.get(proposal.id)
    assert updated.status == "FAILED"
    assert updated.failure_reason == "IB rejected order: insufficient margin"


def test_valid_transition_pending_to_rejected():
    tracker = ProposalTracker()
    proposal = make_stock_proposal()
    tracker.create(proposal)

    ok, reason = tracker.reject(proposal.id)
    assert ok is True
    assert tracker.get(proposal.id).status == "REJECTED"


def test_invalid_transition_approved_to_rejected_fails():
    """APPROVED -> REJECTED is not a valid transition — must fail loudly."""
    tracker = ProposalTracker()
    proposal = make_stock_proposal()
    tracker.create(proposal)

    tracker.approve(proposal.id)
    assert tracker.get(proposal.id).status == "APPROVED"

    ok, reason = tracker.reject(proposal.id)
    assert ok is False
    assert "Invalid transition" in reason
    assert "APPROVED" in reason and "REJECTED" in reason
    # Status must remain unchanged
    assert tracker.get(proposal.id).status == "APPROVED"


def test_cannot_approve_expired_proposal():
    tracker = ProposalTracker()
    proposal = make_stock_proposal(status="EXPIRED")
    tracker.create(proposal)

    ok, reason = tracker.approve(proposal.id)
    assert ok is False
    assert reason == "Cannot approve expired proposal"
    assert tracker.get(proposal.id).status == "EXPIRED"


def test_invalid_transition_executed_to_anything_fails():
    tracker = ProposalTracker()
    proposal = make_stock_proposal(status="EXECUTED")
    tracker.create(proposal)

    ok, reason = tracker.reject(proposal.id)
    assert ok is False
    assert "Invalid transition" in reason


def test_transition_on_unknown_proposal_id():
    tracker = ProposalTracker()
    ok, reason = tracker.approve("nonexistent-id")
    assert ok is False
    assert "not found" in reason


# ─── Duplicate detection ─────────────────────────────────────────────────────

def test_duplicate_detection():
    tracker = ProposalTracker()
    p1 = make_stock_proposal(symbol="TSLA")
    tracker.create(p1)

    assert tracker.has_active_duplicate("TSLA", "stock") is True
    assert tracker.has_active_duplicate("AAPL", "stock") is False
    # Different kind, same symbol — not a duplicate
    assert tracker.has_active_duplicate("TSLA", "option") is False


def test_duplicate_detection_ignores_terminal_statuses():
    tracker = ProposalTracker()
    p1 = make_stock_proposal(symbol="TSLA")
    tracker.create(p1)
    tracker.reject(p1.id)

    assert tracker.has_active_duplicate("TSLA", "stock") is False


def test_duplicate_detection_includes_approved():
    tracker = ProposalTracker()
    p1 = make_stock_proposal(symbol="TSLA")
    tracker.create(p1)
    tracker.approve(p1.id)

    assert tracker.has_active_duplicate("TSLA", "stock") is True


# ─── Daily count rollover ────────────────────────────────────────────────────

def test_daily_executed_count_rollover():
    tracker = ProposalTracker()
    p1 = make_stock_proposal()
    tracker.create(p1)
    tracker.approve(p1.id)
    tracker.mark_executed(p1.id, ib_order_id=1)

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    assert tracker.daily_executed_count(today) == 1
    assert tracker.daily_executed_count(yesterday) == 0
    # Default arg uses today
    assert tracker.daily_executed_count() == 1


def test_daily_executed_count_multiple():
    tracker = ProposalTracker()
    for _ in range(3):
        p = make_stock_proposal(symbol="TSLA")
        tracker.create(p)
        tracker.approve(p.id)
        tracker.mark_executed(p.id, ib_order_id=1)

    assert tracker.daily_executed_count() == 3


# ─── Stale expiry ─────────────────────────────────────────────────────────────

def test_expire_stale_marks_expired_pending_proposals():
    tracker = ProposalTracker()
    expired = make_stock_proposal(expires_in=timedelta(seconds=-1))  # already past
    fresh = make_stock_proposal(expires_in=timedelta(minutes=3))
    tracker.create(expired)
    tracker.create(fresh)

    count = tracker.expire_stale()

    assert count == 1
    assert tracker.get(expired.id).status == "EXPIRED"
    assert tracker.get(fresh.id).status == "PENDING"


def test_expire_stale_does_not_touch_non_pending():
    tracker = ProposalTracker()
    approved = make_stock_proposal(status="APPROVED", expires_in=timedelta(seconds=-1))
    tracker.create(approved)

    count = tracker.expire_stale()

    assert count == 0
    assert tracker.get(approved.id).status == "APPROVED"


# ─── list_pending / list_history ─────────────────────────────────────────────

def test_list_pending_and_history():
    tracker = ProposalTracker()
    p1 = make_stock_proposal(symbol="TSLA")
    p2 = make_option_proposal(symbol="NVDA")
    tracker.create(p1)
    tracker.create(p2)
    tracker.reject(p2.id)

    pending = tracker.list_pending()
    assert len(pending) == 1
    assert pending[0].id == p1.id

    history = tracker.list_history()
    assert len(history) == 2
    ids = {p.id for p in history}
    assert ids == {p1.id, p2.id}


def test_list_history_respects_limit():
    tracker = ProposalTracker()
    for _ in range(5):
        tracker.create(make_stock_proposal(symbol="TSLA"))

    assert len(tracker.list_history(limit=2)) == 2
    assert len(tracker.list_history(limit=20)) == 5


# ─── get_tracker singleton ────────────────────────────────────────────────────

def test_get_tracker_is_singleton():
    from src.orders.tracker import get_tracker
    assert get_tracker() is get_tracker()
