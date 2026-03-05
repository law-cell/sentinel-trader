"""
Rule Model
==========
Dataclass definition for a trading rule.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Rule:
    """
    A single trading rule definition.

    Fields:
        name          Unique human-readable identifier
        symbol        Ticker symbol this rule applies to (e.g. "NVDA")
        condition     Dict describing the condition to evaluate.
                      Must contain "type" key plus condition-specific params.
                      Example: {"type": "price_above", "threshold": 150.0}
        action        Action to fire when condition is met.
                      One of: "log", "console", "notify"
        cooldown      Minimum seconds between consecutive triggers (prevents spam)
        enabled       Whether this rule is active
        last_triggered  Timestamp of last trigger (None = never triggered)
    """

    name: str
    symbol: str
    condition: dict
    action: str
    cooldown: int
    enabled: bool = True
    last_triggered: datetime | None = None

    def is_on_cooldown(self) -> bool:
        """Return True if this rule was triggered recently and is still cooling down."""
        if self.last_triggered is None:
            return False
        elapsed = (datetime.now() - self.last_triggered).total_seconds()
        return elapsed < self.cooldown

    def mark_triggered(self):
        """Record that this rule just fired."""
        self.last_triggered = datetime.now()
