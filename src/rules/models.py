"""
Rule Model
==========
Pydantic models for a trading rule and its trigger action.

A Rule has two independent concerns:
    channel   How an alert is delivered ("telegram", "console", "log", "notify")
    action    What happens when the condition fires:
                - AlertAction          : send an alert via `channel` (default)
                - StockOrderAction     : propose a stock order (not yet executed)
                - OptionOrderAction    : propose an option order (not yet executed)

Legacy rules.json entries store the old delivery-channel name directly in the
`action` field (e.g. "action": "telegram"). The model_validator below migrates
those on load: the string becomes `channel`, and `action` defaults to
AlertAction.
"""

from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ─── Action types ─────────────────────────────────────────────────────────────

class AlertAction(BaseModel):
    """Send a Telegram/console/log alert via the rule's `channel`. Default action."""
    type: Literal["alert"] = "alert"


class StockOrderAction(BaseModel):
    """On trigger, propose a stock order for the user to approve (execution: Sunday)."""
    type: Literal["propose_stock_order"]
    side: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Optional[float] = None  # required if order_type == "LIMIT"


class OptionOrderAction(BaseModel):
    """
    On trigger, propose an option order for the user to approve (execution: Sunday).

    Sell-to-open only per safety policy — side and order_type are not
    user-specified; they are forced by the executor (OPTION_SIDE_ALLOWED,
    OPTION_ORDER_TYPE_FORCED in src/config/settings.py).
    """
    type: Literal["propose_option_order"]
    right: Literal["C", "P"]
    strike: float
    expiry_days: int  # days from rule trigger time
    quantity: int = 1


Action = Annotated[
    Union[AlertAction, StockOrderAction, OptionOrderAction],
    Field(discriminator="type"),
]


# ─── Rule ───────────────────────────────────────────────────────────────────────

class Rule(BaseModel):
    """
    A single trading rule definition.

    Fields:
        name          Unique human-readable identifier
        symbol        Ticker symbol this rule applies to (e.g. "NVDA")
        condition     Dict describing the condition to evaluate.
                      Must contain "type" key plus condition-specific params.
                      Example: {"type": "price_above", "threshold": 150.0}
        channel       Delivery channel for alerts: "log", "console", "telegram", "notify"
        action        What happens when the condition is met. Defaults to AlertAction.
        cooldown      Minimum seconds between consecutive triggers (prevents spam)
        enabled       Whether this rule is active
        last_triggered  Timestamp of last trigger (None = never triggered, in-memory only)
    """

    name: str
    symbol: str
    condition: dict
    channel: str = "telegram"
    action: Action = Field(default_factory=AlertAction)
    cooldown: int
    enabled: bool = True
    last_triggered: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_action(cls, data):
        """
        Migrate legacy rules.json entries where `action` was the delivery
        channel name (e.g. "telegram"). New format stores delivery channel
        in `channel` and trigger behaviour in `action` (Action union).
        """
        if not isinstance(data, dict):
            return data

        action = data.get("action")
        if isinstance(action, str):
            data = dict(data)
            data.setdefault("channel", action)
            data["action"] = {"type": "alert"}
        elif action is None:
            data = dict(data)
            data["action"] = {"type": "alert"}

        return data

    def is_on_cooldown(self) -> bool:
        """Return True if this rule was triggered recently and is still cooling down."""
        if self.last_triggered is None:
            return False
        elapsed = (datetime.now() - self.last_triggered).total_seconds()
        return elapsed < self.cooldown

    def mark_triggered(self):
        """Record that this rule just fired."""
        self.last_triggered = datetime.now()
