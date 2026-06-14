"""
LLM Tool Definitions
=====================
Anthropic tool-use schemas for extracting a structured Rule from a
natural-language instruction (POST /api/rules/from-nl).

Claude is given exactly these three tools and must call exactly one.
Each tool maps to one of the Action types in src/rules/models.py:

    create_alert_rule         -> AlertAction
    create_stock_order_rule   -> StockOrderAction
    create_option_order_rule  -> OptionOrderAction

Design note — "make invalid states unrepresentable":
    Fields that are hardcoded by safety policy (src/config/settings.py)
    are deliberately OMITTED from these schemas, not just defensively
    validated later:
      - create_option_order_rule has no `side` field — OPTION_SIDE_ALLOWED
        forces sell-to-open, so the LLM cannot ask for a buy.
      - create_option_order_rule has no `order_type` field —
        OPTION_ORDER_TYPE_FORCED is always "LIMIT".
    Stock orders keep `side` and `order_type` configurable since BUY/SELL
    and MARKET/LIMIT are legitimate user choices for equities.
"""

# Condition shared by all three tools: what triggers the rule.
_CONDITION_SCHEMA = {
    "type": "object",
    "description": "The market condition that triggers this rule.",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["price_above", "price_below", "price_change_pct", "volume_above"],
            "description": (
                "price_above/price_below: last price vs threshold (USD). "
                "price_change_pct: % change from previous close vs threshold "
                "(use a negative threshold for a drop, e.g. -5.0 for 'drops 5%'). "
                "volume_above: cumulative volume vs threshold."
            ),
        },
        "symbol": {
            "type": "string",
            "description": "Ticker symbol this rule watches, e.g. 'NVDA'.",
        },
        "threshold": {
            "type": "number",
            "description": (
                "The trigger value. For price_above/price_below: target price "
                "in USD. For volume_above: target volume in shares. For "
                "price_change_pct: signed percentage from previous session "
                "close — use negative for drops (e.g. -5.0 means drops 5%), "
                "positive for gains (5.0 means rises 5%)."
            ),
        },
    },
    "required": ["type", "symbol", "threshold"],
}

_COOLDOWN_SCHEMA = {
    "type": "integer",
    "description": "Minimum seconds between consecutive triggers of this rule.",
    "default": 3600,
    "minimum": 60,
}


CREATE_ALERT_RULE = {
    "name": "create_alert_rule",
    "description": (
        "Create a rule that sends a Telegram alert when the trigger condition "
        "is met. Use this when the user only wants to be notified — no order "
        "placement is mentioned."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short, human-readable name for this rule.",
            },
            "condition": _CONDITION_SCHEMA,
            "cooldown_seconds": _COOLDOWN_SCHEMA,
        },
        "required": ["name", "condition"],
    },
}


CREATE_STOCK_ORDER_RULE = {
    "name": "create_stock_order_rule",
    "description": (
        "Create a rule that, when the trigger fires, proposes a stock order "
        "for the user to approve via Telegram. Use this when the user mentions "
        "buying or selling shares of a stock by name."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short, human-readable name for this rule.",
            },
            "condition": _CONDITION_SCHEMA,
            "cooldown_seconds": _COOLDOWN_SCHEMA,
            "side": {
                "type": "string",
                "enum": ["BUY", "SELL"],
                "description": "Whether the proposed order buys or sells shares.",
            },
            "quantity": {
                "type": "integer",
                "description": "Number of shares.",
                "minimum": 1,
            },
            "order_type": {
                "type": "string",
                "enum": ["MARKET", "LIMIT"],
                "description": "Order type for the proposed stock order.",
            },
            "limit_price": {
                "type": "number",
                "description": (
                    "Limit price in USD. Required when order_type is 'LIMIT'. "
                    "Omit entirely when order_type is 'MARKET'."
                ),
            },
        },
        "required": ["name", "condition", "side", "quantity", "order_type"],
    },
}


CREATE_OPTION_ORDER_RULE = {
    "name": "create_option_order_rule",
    "description": (
        "Create a rule that, when the trigger fires, proposes an option order "
        "for the user to approve via Telegram. Use this when the user mentions "
        "options strategies — covered calls, cash-secured puts, selling calls, "
        "selling puts. ONLY sell-to-open orders are supported; do not use this "
        "tool for buying options."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Short, human-readable name for this rule.",
            },
            "condition": _CONDITION_SCHEMA,
            "cooldown_seconds": _COOLDOWN_SCHEMA,
            "right": {
                "type": "string",
                "enum": ["C", "P"],
                "description": "Option right: 'C' for call, 'P' for put.",
            },
            "strike": {
                "type": "number",
                "description": "Strike price in USD.",
            },
            "expiry_days": {
                "type": "integer",
                "description": (
                    "Days from rule trigger time until option expiry. "
                    "Convert relative dates (e.g. 'in 30 days', 'next month') "
                    "to an integer day count."
                ),
                "minimum": 1,
                "maximum": 60,
            },
            "quantity": {
                "type": "integer",
                "description": "Number of contracts.",
                "default": 1,
                "minimum": 1,
            },
        },
        "required": ["name", "condition", "right", "strike", "expiry_days"],
    },
}


RULE_TOOLS = [CREATE_ALERT_RULE, CREATE_STOCK_ORDER_RULE, CREATE_OPTION_ORDER_RULE]
