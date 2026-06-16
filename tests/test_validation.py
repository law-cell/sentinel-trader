"""
Unit tests for the pre-trade validation pipeline.

Run: pytest tests/test_validation.py -v
"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from src.config.settings import (
    ALLOWED_SYMBOLS,
    MAX_NOTIONAL_PER_ORDER_USD,
    MAX_EXECUTED_ORDERS_PER_DAY,
    MAX_OPTION_PREMIUM_USD,
    MAX_OPTION_EXPIRY_DAYS,
)
from src.orders.models import StockOrderProposal, OptionOrderProposal
from src.orders.tracker import ProposalTracker
from src.orders import validation as v


# ─── Fixtures / helpers ──────────────────────────────────────────────────────

class FakeIB:
    def __init__(self, connected: bool = True):
        self._connected = connected

    def isConnected(self) -> bool:
        return self._connected


ALLOWED_SYMBOL = "NVDA"
DISALLOWED_SYMBOL = "SPY"
assert ALLOWED_SYMBOL in ALLOWED_SYMBOLS
assert DISALLOWED_SYMBOL not in ALLOWED_SYMBOLS


def make_stock_proposal(
    symbol: str = ALLOWED_SYMBOL,
    status: str = "PENDING",
    notional: float = 1000.0,
    expires_in: timedelta = timedelta(minutes=3),
) -> StockOrderProposal:
    now = datetime.now()
    return StockOrderProposal(
        id=str(uuid.uuid4()),
        rule_id="r1",
        rule_name="r1",
        symbol=symbol,
        created_at=now,
        expires_at=now + expires_in,
        status=status,
        estimated_notional_usd=notional,
        trigger_price=100.0,
        side="BUY",
        quantity=10,
        order_type="MARKET",
    )


def make_option_proposal(
    symbol: str = ALLOWED_SYMBOL,
    status: str = "PENDING",
    notional: float = 250.0,
    quantity: int = 1,
    expiry_days: int = 30,
    expires_in: timedelta = timedelta(minutes=3),
) -> OptionOrderProposal:
    now = datetime.now()
    return OptionOrderProposal(
        id=str(uuid.uuid4()),
        rule_id="r2",
        rule_name="r2",
        symbol=symbol,
        created_at=now,
        expires_at=now + expires_in,
        status=status,
        estimated_notional_usd=notional,
        trigger_price=220.0,
        right="C",
        strike=240.0,
        expiry_date=date.today() + timedelta(days=expiry_days),
        quantity=quantity,
    )


# ─── check_paper_mode_only ────────────────────────────────────────────────────

def test_check_paper_mode_only_passes_in_paper_mode():
    assert v.check_paper_mode_only().ok is True


# ─── check_proposal_status_is ─────────────────────────────────────────────────

def test_check_proposal_status_is_pass():
    p = make_stock_proposal(status="PENDING")
    assert v.check_proposal_status_is(p, "PENDING").ok is True


def test_check_proposal_status_is_fail():
    p = make_stock_proposal(status="PENDING")
    result = v.check_proposal_status_is(p, "APPROVED")
    assert result.ok is False
    assert "PENDING" in result.reason and "APPROVED" in result.reason


# ─── check_proposal_not_expired ──────────────────────────────────────────────

def test_check_proposal_not_expired_pass():
    p = make_stock_proposal(expires_in=timedelta(minutes=3))
    assert v.check_proposal_not_expired(p).ok is True


def test_check_proposal_not_expired_fail():
    p = make_stock_proposal(expires_in=timedelta(seconds=-1))
    result = v.check_proposal_not_expired(p)
    assert result.ok is False
    assert "expired" in result.reason


# ─── check_symbol_in_allowlist + case sensitivity ────────────────────────────

def test_check_symbol_in_allowlist_pass():
    assert v.check_symbol_in_allowlist("NVDA").ok is True


def test_check_symbol_in_allowlist_fail_not_allowed():
    result = v.check_symbol_in_allowlist("SPY")
    assert result.ok is False
    assert "SPY" in result.reason


def test_check_symbol_in_allowlist_lowercase_does_not_slip_through():
    """'nvda' must NOT pass even though 'NVDA' is allowed — no implicit normalization."""
    result = v.check_symbol_in_allowlist("nvda")
    assert result.ok is False
    assert "nvda" in result.reason


# ─── check_no_active_duplicate ───────────────────────────────────────────────

def test_check_no_active_duplicate_pass_when_none_exists():
    tracker = ProposalTracker()
    p = make_stock_proposal()
    assert v.check_no_active_duplicate(p, tracker).ok is True


def test_check_no_active_duplicate_fail_when_duplicate_exists():
    tracker = ProposalTracker()
    existing = make_stock_proposal(symbol="NVDA")
    tracker.create(existing)

    new = make_stock_proposal(symbol="NVDA")
    result = v.check_no_active_duplicate(new, tracker)
    assert result.ok is False
    assert "NVDA" in result.reason


def test_check_no_active_duplicate_excludes_self():
    """A proposal already in the tracker (Pass 2) must not be its own duplicate."""
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA")
    tracker.create(p)

    assert v.check_no_active_duplicate(p, tracker).ok is True


# ─── check_daily_executed_under_cap — boundary tests ─────────────────────────

def test_daily_cap_4_executed_5th_proposal_passes():
    tracker = ProposalTracker()
    for _ in range(4):
        p = make_stock_proposal()
        tracker.create(p)
        tracker.approve(p.id)
        tracker.mark_executed(p.id, ib_order_id=1)

    assert tracker.daily_executed_count() == 4
    assert MAX_EXECUTED_ORDERS_PER_DAY == 5
    assert v.check_daily_executed_under_cap(tracker).ok is True


def test_daily_cap_5_executed_6th_proposal_fails():
    tracker = ProposalTracker()
    for _ in range(5):
        p = make_stock_proposal()
        tracker.create(p)
        tracker.approve(p.id)
        tracker.mark_executed(p.id, ib_order_id=1)

    assert tracker.daily_executed_count() == 5
    result = v.check_daily_executed_under_cap(tracker)
    assert result.ok is False
    assert "5/5" in result.reason


# ─── check_option_expiry_within_max — boundary tests ─────────────────────────

def test_option_expiry_60_days_passes():
    assert MAX_OPTION_EXPIRY_DAYS == 60
    p = make_option_proposal(expiry_days=60)
    assert v.check_option_expiry_within_max(p).ok is True


def test_option_expiry_61_days_fails():
    p = make_option_proposal(expiry_days=61)
    result = v.check_option_expiry_within_max(p)
    assert result.ok is False
    assert "61" in result.reason


def test_option_expiry_1_day_passes():
    p = make_option_proposal(expiry_days=1)
    assert v.check_option_expiry_within_max(p).ok is True


def test_option_expiry_0_days_fails():
    p = make_option_proposal(expiry_days=0)
    result = v.check_option_expiry_within_max(p)
    assert result.ok is False
    assert "not at least 1 day out" in result.reason


# ─── check_option_premium_estimate_under_cap — boundary tests ────────────────

def test_option_premium_5_00_passes():
    assert MAX_OPTION_PREMIUM_USD == 5.0
    # quantity=1 -> notional = premium * 100
    p = make_option_proposal(quantity=1, notional=500.0)
    assert v.check_option_premium_estimate_under_cap(p).ok is True


def test_option_premium_5_01_fails():
    p = make_option_proposal(quantity=1, notional=501.0)
    result = v.check_option_premium_estimate_under_cap(p)
    assert result.ok is False
    assert "5.01" in result.reason


# ─── check_notional_within_limit — boundary tests ────────────────────────────

def test_notional_exactly_2000_passes():
    assert MAX_NOTIONAL_PER_ORDER_USD == 2000.0
    p = make_stock_proposal(notional=2000.00)
    assert v.check_notional_within_limit(p).ok is True


def test_notional_2000_01_fails():
    p = make_stock_proposal(notional=2000.01)
    result = v.check_notional_within_limit(p)
    assert result.ok is False
    assert "2,000.01" in result.reason


def test_notional_1999_99_passes():
    p = make_stock_proposal(notional=1999.99)
    assert v.check_notional_within_limit(p).ok is True


# ─── check_ib_connected ───────────────────────────────────────────────────────

def test_ib_connected_pass():
    assert v.check_ib_connected(FakeIB(connected=True)).ok is True


def test_ib_connected_fail_when_disconnected():
    result = v.check_ib_connected(FakeIB(connected=False))
    assert result.ok is False


def test_ib_connected_fail_when_none():
    result = v.check_ib_connected(None)
    assert result.ok is False


# ─── Composition: validate_for_proposal ──────────────────────────────────────

def test_validate_for_proposal_all_pass():
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=1000.0)
    result = v.validate_for_proposal(p, tracker, ib=FakeIB(True))
    assert result.ok is True


def test_validate_for_proposal_fails_at_symbol_allowlist_short_circuits():
    """Symbol check (position 4) fails — must NOT report a later check's reason
    even though a later check (e.g. notional) would also fail."""
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="SPY", notional=999999.0)  # also violates notional
    result = v.validate_for_proposal(p, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "SPY" in result.reason
    assert "allowed symbol list" in result.reason
    assert "notional" not in result.reason


def test_validate_for_proposal_fails_at_duplicate_short_circuits():
    """Duplicate check (position 5) fails — must not report daily-cap or
    notional reasons, even if those would also fail."""
    tracker = ProposalTracker()
    existing = make_stock_proposal(symbol="NVDA")
    tracker.create(existing)

    new = make_stock_proposal(symbol="NVDA", notional=999999.0)
    result = v.validate_for_proposal(new, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "active" in result.reason.lower() and "NVDA" in result.reason
    assert "notional" not in result.reason


def test_validate_for_proposal_fails_at_notional_when_earlier_checks_pass():
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=5000.0)
    result = v.validate_for_proposal(p, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "notional" in result.reason.lower()


def test_validate_for_proposal_fails_at_ib_connected_last():
    """All other checks pass, IB disconnected -> IB check is the reported failure."""
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=1000.0)
    result = v.validate_for_proposal(p, tracker, ib=FakeIB(False))
    assert result.ok is False
    assert "IB" in result.reason


def test_validate_for_proposal_option_checks():
    tracker = ProposalTracker()
    bad_expiry = make_option_proposal(symbol="NVDA", expiry_days=90, notional=250.0)
    result = v.validate_for_proposal(bad_expiry, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "expiry" in result.reason.lower()

    bad_premium = make_option_proposal(symbol="NVDA", expiry_days=30, quantity=1, notional=600.0)
    result = v.validate_for_proposal(bad_premium, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "premium" in result.reason.lower()


# ─── Composition: validate_for_execution ─────────────────────────────────────

def test_validate_for_execution_all_pass():
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=1000.0, status="APPROVED")
    tracker.create(p)
    result = v.validate_for_execution(p, tracker, ib=FakeIB(True))
    assert result.ok is True


def test_validate_for_execution_fails_if_status_not_approved():
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=1000.0, status="PENDING")
    tracker.create(p)
    result = v.validate_for_execution(p, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "PENDING" in result.reason and "APPROVED" in result.reason


def test_validate_for_execution_fails_if_expired_since_proposal():
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=1000.0, status="APPROVED", expires_in=timedelta(seconds=-1))
    tracker.create(p)
    result = v.validate_for_execution(p, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "expired" in result.reason


def test_validate_for_execution_fails_if_daily_cap_hit_by_other_proposal():
    tracker = ProposalTracker()
    # Fill the daily cap with a different proposal
    for _ in range(MAX_EXECUTED_ORDERS_PER_DAY):
        other = make_stock_proposal(symbol="AAPL")
        tracker.create(other)
        tracker.approve(other.id)
        tracker.mark_executed(other.id, ib_order_id=1)

    p = make_stock_proposal(symbol="NVDA", notional=1000.0, status="APPROVED")
    tracker.create(p)
    result = v.validate_for_execution(p, tracker, ib=FakeIB(True))
    assert result.ok is False
    assert "Daily executed order limit" in result.reason


def test_validate_for_execution_does_not_flag_self_as_duplicate():
    tracker = ProposalTracker()
    p = make_stock_proposal(symbol="NVDA", notional=1000.0, status="APPROVED")
    tracker.create(p)
    result = v.validate_for_execution(p, tracker, ib=FakeIB(True))
    assert result.ok is True
