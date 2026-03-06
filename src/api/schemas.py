"""
API Schemas
===========
Pydantic models for request validation and response serialization.
"""

from datetime import datetime
from pydantic import BaseModel, field_validator


# ─── Rules ────────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str
    symbol: str
    condition: dict
    action: str
    cooldown: int
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.upper()

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"log", "console", "telegram", "notify"}
        if v not in allowed:
            raise ValueError(f"action must be one of {allowed}")
        return v

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


class RuleUpdate(BaseModel):
    """All fields optional — only provided fields are updated."""
    condition: dict | None = None
    action: str | None = None
    cooldown: int | None = None
    enabled: bool | None = None


class RuleResponse(BaseModel):
    name: str
    symbol: str
    condition: dict
    action: str
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
