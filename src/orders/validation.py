"""
Pre-trade Validation Pipeline
==============================
Two passes over the same set of checks:

  Pass 1 — validate_for_proposal(proposal, tracker, ib=None)
    Run when the rule engine creates a proposal, BEFORE sending it to
    the user. Rejects early so the user isn't bothered with proposals
    that would always fail.

  Pass 2 — validate_for_execution(proposal, tracker, ib=None)
    Run when the user approves a proposal, BEFORE calling placeOrder.
    State may have changed since proposal creation (IB might have
    disconnected, the daily cap may have been hit by a different
    proposal, etc).

Each check returns a CheckResult(ok, reason). The pipelines short-circuit
on the first failing check and return its CheckResult — callers get one
specific, actionable reason rather than a list.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from src.config.settings import (
    ALLOWED_SYMBOLS,
    MAX_NOTIONAL_PER_ORDER_USD,
    MAX_EXECUTED_ORDERS_PER_DAY,
    MAX_OPTION_PREMIUM_USD,
    MAX_OPTION_EXPIRY_DAYS,
    TRADING_MODE,
)
from src.orders.models import OptionOrderProposal, Proposal
from src.orders.tracker import ProposalTracker


@dataclass
class CheckResult:
    ok: bool
    reason: str = "ok"


# ─── Individual checks ────────────────────────────────────────────────────
# Symbols are NOT case-normalized here. Proposals (and the rules they're
# built from) are required to carry uppercase symbols already — see
# RuleCreate.uppercase_symbol. A lowercase symbol reaching this check is
# treated as a defect and fails rather than silently passing.

def check_paper_mode_only() -> CheckResult:
    if TRADING_MODE != "paper":
        return CheckResult(False, f"TRADING_MODE is '{TRADING_MODE}', not 'paper' — refusing to process order proposals")
    return CheckResult(True)


def check_proposal_status_is(proposal: Proposal, expected: str) -> CheckResult:
    if proposal.status != expected:
        return CheckResult(False, f"Proposal {proposal.id} has status '{proposal.status}', expected '{expected}'")
    return CheckResult(True)


def check_proposal_not_expired(proposal: Proposal) -> CheckResult:
    if proposal.expires_at <= datetime.now():
        return CheckResult(False, f"Proposal {proposal.id} expired at {proposal.expires_at.isoformat()}")
    return CheckResult(True)


def check_symbol_in_allowlist(symbol: str) -> CheckResult:
    if symbol not in ALLOWED_SYMBOLS:
        return CheckResult(False, f"Symbol '{symbol}' is not in the allowed symbol list: {sorted(ALLOWED_SYMBOLS)}")
    return CheckResult(True)


def check_no_active_duplicate(proposal: Proposal, tracker: ProposalTracker) -> CheckResult:
    if tracker.has_active_duplicate(proposal.symbol, proposal.kind, exclude_id=proposal.id):
        return CheckResult(False, f"An active {proposal.kind} proposal already exists for {proposal.symbol}")
    return CheckResult(True)


def check_daily_executed_under_cap(tracker: ProposalTracker) -> CheckResult:
    count = tracker.daily_executed_count()
    if count >= MAX_EXECUTED_ORDERS_PER_DAY:
        return CheckResult(False, f"Daily executed order limit reached ({count}/{MAX_EXECUTED_ORDERS_PER_DAY})")
    return CheckResult(True)


def check_option_expiry_within_max(proposal: OptionOrderProposal) -> CheckResult:
    days_out = (proposal.expiry_date - date.today()).days
    if days_out < 1:
        return CheckResult(False, f"Option expiry {proposal.expiry_date.isoformat()} is not at least 1 day out")
    if days_out > MAX_OPTION_EXPIRY_DAYS:
        return CheckResult(False, f"Option expiry is {days_out} days out, exceeds max of {MAX_OPTION_EXPIRY_DAYS} days")
    return CheckResult(True)


def check_option_premium_estimate_under_cap(proposal: OptionOrderProposal) -> CheckResult:
    contracts = proposal.quantity * 100
    premium = round(proposal.estimated_notional_usd / contracts, 2)
    if premium > MAX_OPTION_PREMIUM_USD:
        return CheckResult(False, f"Estimated premium ${premium:.2f}/contract exceeds max of ${MAX_OPTION_PREMIUM_USD:.2f}")
    return CheckResult(True)


def check_notional_within_limit(proposal: Proposal) -> CheckResult:
    if proposal.estimated_notional_usd > MAX_NOTIONAL_PER_ORDER_USD:
        return CheckResult(False, f"Estimated notional ${proposal.estimated_notional_usd:,.2f} exceeds max of ${MAX_NOTIONAL_PER_ORDER_USD:,.2f} per order")
    return CheckResult(True)


def check_ib_connected(ib) -> CheckResult:
    if ib is None or not ib.isConnected():
        return CheckResult(False, "IB is not connected — cannot process order proposal")
    return CheckResult(True)


# ─── Pipelines ─────────────────────────────────────────────────────────────

def _run_checks(checks: list[Callable[[], CheckResult]]) -> CheckResult:
    """Run each check lazily, in order, returning the first failure (or ok)."""
    for check in checks:
        result = check()
        if not result.ok:
            return result
    return CheckResult(True)


def _build_pipeline(proposal: Proposal, tracker: ProposalTracker, ib, status_check: Callable[[], CheckResult]) -> list[Callable[[], CheckResult]]:
    checks: list[Callable[[], CheckResult]] = [
        check_paper_mode_only,
        status_check,
        lambda: check_proposal_not_expired(proposal),
        lambda: check_symbol_in_allowlist(proposal.symbol),
        lambda: check_no_active_duplicate(proposal, tracker),
        lambda: check_daily_executed_under_cap(tracker),
    ]
    if isinstance(proposal, OptionOrderProposal):
        checks.append(lambda: check_option_expiry_within_max(proposal))
        checks.append(lambda: check_option_premium_estimate_under_cap(proposal))
    checks.append(lambda: check_notional_within_limit(proposal))
    checks.append(lambda: check_ib_connected(ib))
    return checks


def validate_for_proposal(proposal: Proposal, tracker: ProposalTracker, ib=None) -> CheckResult:
    """
    Run before a freshly-built proposal is shown to the user.

    Check order (cheap -> expensive, so the common failure paths short-circuit
    fast and never reach IB):
      1. paper mode               - constant, microsecond
      2. proposal status (PENDING) - dict lookup
      3. not expired               - datetime comparison
      4. symbol allowlist          - set lookup
      5. no active duplicate       - iterate tracker
      6. daily cap                 - dict lookup
      7. option expiry (if option) - datetime arithmetic
      8. option premium (if option)- arithmetic on stored estimate
      9. notional limit            - arithmetic
     10. IB connected              - attribute access (last: only matters
                                      if everything else about the proposal
                                      itself is already valid)
    """
    return _run_checks(_build_pipeline(proposal, tracker, ib, lambda: check_proposal_status_is(proposal, "PENDING")))


def validate_for_execution(proposal: Proposal, tracker: ProposalTracker, ib=None) -> CheckResult:
    """
    Run when the user approves a proposal, before placeOrder. Same pipeline
    as validate_for_proposal (see its docstring for ordering rationale),
    except step 2 requires status == APPROVED rather than PENDING — state
    may have drifted since the proposal was created (IB disconnect, another
    proposal hitting the daily cap, the proposal itself expiring, etc).
    """
    return _run_checks(_build_pipeline(proposal, tracker, ib, lambda: check_proposal_status_is(proposal, "APPROVED")))
