"""
Order Proposal Models
======================
A Proposal is created when a rule with action.type in
("propose_stock_order", "propose_option_order") triggers. It represents
an order that has passed pre-trade validation and is awaiting user
approval before (eventually) being sent to IB.

Two pydantic models sharing a base, discriminated by `kind`.
"""

from datetime import date, datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class ProposalBase(BaseModel):
    id: str                  # uuid4
    rule_id: str
    # TODO: Rules currently identified by `name` (no UUID). Proposals
    # reference rule_name captured at creation time. If a rule is
    # renamed during a 3-min pending window, the proposal becomes
    # orphaned. Acceptable for single-user dev tool. To fix: add
    # stable rule.id (UUID) and reference by id.
    rule_name: str            # for human display
    symbol: str
    created_at: datetime
    expires_at: datetime      # created_at + PROPOSAL_EXPIRY_SECONDS
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED", "FAILED"]
    estimated_notional_usd: float
    ib_order_id: Optional[int] = None          # populated after EXECUTED
    failure_reason: Optional[str] = None       # populated if FAILED
    telegram_message_id: Optional[int] = None  # message_id of the sent proposal message
    # Market snapshot at proposal time, for audit
    trigger_price: float


class StockOrderProposal(ProposalBase):
    kind: Literal["stock"] = "stock"
    side: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Optional[float] = None


class OptionOrderProposal(ProposalBase):
    kind: Literal["option"] = "option"
    right: Literal["C", "P"]
    strike: float
    expiry_date: date         # absolute date computed from expiry_days
    quantity: int
    # side and order_type intentionally absent — hardcoded SELL/LIMIT
    # limit_price computed at dispatch time from bid-ask mid (Sunday afternoon)
    limit_price: Optional[float] = None


Proposal = Annotated[
    Union[StockOrderProposal, OptionOrderProposal],
    Field(discriminator="kind"),
]
