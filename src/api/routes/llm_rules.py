"""
Natural-Language Rule Creation
===============================
POST /api/rules/from-nl — turn a natural-language instruction into a
structured Rule via Claude tool-use, validate it against the safety
policy, and persist it (unless dry_run).

Flow:
    1. extract_rule(prompt) -> Claude tool_use call (or text-only response)
    2. No tool call -> 400, Claude's text as detail
    3. Build a Rule from the tool's input
    4. validate_rule(rule) -> list of errors
    5. errors -> status="invalid", rule NOT saved
       no errors -> status="ok", saved unless dry_run
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, Request

from src.rules.models import Rule, AlertAction, StockOrderAction, OptionOrderAction
from src.rules.loader import save_rules_to_file
from src.api.schemas import FromNLRequest, FromNLResponse, RuleResponse
from src.api.routes.rules import _to_response
from src.llm.extraction import extract_rule
from src.llm.validator import validate_rule

router = APIRouter(prefix="/api/rules", tags=["rules"])

RULES_FILE = Path("rules.json")


def _build_rule(tool_name: str, tool_input: dict) -> Rule:
    """Construct a Rule from a tool_use call's input."""
    condition = tool_input["condition"]
    name = tool_input["name"]
    symbol = condition["symbol"].upper()
    cooldown = tool_input.get("cooldown_seconds", 3600)
    rule_condition = {"type": condition["type"], "threshold": condition["threshold"]}

    if tool_name == "create_alert_rule":
        action = AlertAction()

    elif tool_name == "create_stock_order_rule":
        action = StockOrderAction(
            type="propose_stock_order",
            side=tool_input["side"],
            quantity=tool_input["quantity"],
            order_type=tool_input["order_type"],
            limit_price=tool_input.get("limit_price"),
        )

    elif tool_name == "create_option_order_rule":
        action = OptionOrderAction(
            type="propose_option_order",
            right=tool_input["right"],
            strike=tool_input["strike"],
            expiry_days=tool_input["expiry_days"],
            quantity=tool_input.get("quantity", 1),
        )

    else:
        raise HTTPException(status_code=500, detail=f"Unknown tool: {tool_name}")

    return Rule(
        name=name,
        symbol=symbol,
        condition=rule_condition,
        channel="telegram",
        action=action,
        cooldown=cooldown,
    )


@router.post("/from-nl", response_model=FromNLResponse)
async def create_rule_from_nl(request: Request, body: FromNLRequest):
    """Extract a Rule from a natural-language prompt via Claude, validate, and persist."""
    extracted = extract_rule(body.prompt)

    if "text" not in extracted:
        tool_name = extracted["tool_name"]
        tool_input = extracted["tool_input"]
    else:
        raise HTTPException(status_code=400, detail=extracted["text"])

    rule = _build_rule(tool_name, tool_input)
    errors = validate_rule(rule)

    if errors:
        return FromNLResponse(status="invalid", rule=_to_response(rule), errors=errors, saved=False)

    saved = False
    if not body.dry_run:
        engine = request.app.state.engine

        if engine.find_rule(rule.name):
            raise HTTPException(status_code=409, detail=f"Rule '{rule.name}' already exists")

        engine.add_rule(rule)

        ib = getattr(request.app.state, "ib", None)
        if ib is not None and engine._stream is not None:
            await engine.subscribe_symbol(rule.symbol)

        save_rules_to_file(engine.all_rules, RULES_FILE)
        saved = True

    return FromNLResponse(status="ok", rule=_to_response(rule), errors=[], saved=saved)
