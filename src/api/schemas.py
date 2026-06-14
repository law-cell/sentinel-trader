"""
API Schemas
===========
Pydantic models for request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, field_validator, model_validator

from src.rules.models import Action

_ALLOWED_CHANNELS = {"log", "console", "telegram", "notify"}


# ─── Rules ────────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str
    symbol: str
    condition: dict
    # `channel` is the new field for delivery channel ("telegram", "console", ...).
    # `action` is the new Action union ({"type": "alert" | "propose_stock_order" | ...}).
    # Legacy clients may still send `action` as a plain channel-name string
    # (e.g. "telegram") — this is migrated to `channel` + AlertAction below.
    channel: str | None = None
    action: str | dict | None = None
    cooldown: int
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.upper()

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: dict) -> dict:
        allowed_types = {"price_above", "price_below", "price_change_pct", "volume_above"}
        if "type" not in v:
            raise ValueError("condition must have a 'type' field")
        if v["type"] not in allowed_types:
            raise ValueError(f"condition type must be one of {allowed_types}")
        if "threshold" not in v:
            raise ValueError("condition must have a 'threshold' field")
        return v

    @model_validator(mode="after")
    def _resolve_channel_and_action(self):
        # Legacy format: `action` was the delivery-channel name.
        if isinstance(self.action, str):
            if self.channel is None:
                self.channel = self.action
            self.action = {"type": "alert"}

        if self.channel is None:
            self.channel = "telegram"
        if self.channel not in _ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of {_ALLOWED_CHANNELS}")

        if self.action is None:
            self.action = {"type": "alert"}

        return self


class RuleUpdate(BaseModel):
    """All fields optional — only provided fields are updated."""
    condition: dict | None = None
    channel: str | None = None
    cooldown: int | None = None
    enabled: bool | None = None


class RuleResponse(BaseModel):
    name: str
    symbol: str
    condition: dict
    channel: str
    action: Action
    cooldown: int
    enabled: bool
    last_triggered: datetime | None


class TriggerEvent(BaseModel):
    timestamp: str
    rule_name: str
    symbol: str
    price: float


# ─── Symbol search ────────────────────────────────────────────────────────────

class SymbolSearchResult(BaseModel):
    symbol: str
    name: str
    sec_type: str
    exchange: str


# ─── Account ──────────────────────────────────────────────────────────────────

class AccountSummaryResponse(BaseModel):
    account: str
    summary: dict[str, float | None]


class PositionResponse(BaseModel):
    symbol: str
    sec_type: str
    exchange: str
    position: float
    avg_cost: float | None


class MarketDataResponse(BaseModel):
    symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    volume: float | None
    close: float | None
