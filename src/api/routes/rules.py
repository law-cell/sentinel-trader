"""
Rules API Routes
================
CRUD endpoints for trading rules + trigger history.

Endpoints:
    GET    /api/rules           — list all rules
    GET    /api/rules/history   — recent trigger events (in-memory)
    POST   /api/rules           — create a new rule
    PUT    /api/rules/{name}    — update an existing rule
    DELETE /api/rules/{name}    — delete a rule
"""

from datetime import datetime
from pathlib import Path
from ib_async import Ticker
from fastapi import APIRouter, HTTPException, Request

from src.config.settings import ENABLE_TEST_TRIGGER
from src.rules.actions import execute_rule_action
from src.rules.conditions import evaluate_condition
from src.rules.models import Rule
from src.rules.loader import save_rules_to_file
from src.api.schemas import RuleCreate, RuleUpdate, RuleResponse, TriggerEvent, TriggerTestRequest, TriggerTestResponse

router = APIRouter(prefix="/api/rules", tags=["rules"])

RULES_FILE = Path("rules.json")


def _to_response(rule: Rule) -> RuleResponse:
    return RuleResponse(
        name=rule.name,
        symbol=rule.symbol,
        condition=rule.condition,
        channel=rule.channel,
        action=rule.action,
        cooldown=rule.cooldown,
        enabled=rule.enabled,
        last_triggered=rule.last_triggered,
    )


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[RuleResponse])
async def list_rules(request: Request):
    """Return all loaded rules."""
    engine = request.app.state.engine
    return [_to_response(r) for r in engine.all_rules]


# NOTE: /history must be declared before /{name} to avoid being captured as a
# path parameter match.
@router.get("/history", response_model=list[TriggerEvent])
async def get_history(request: Request, limit: int = 50):
    """Return the most recent rule trigger events (max 100 stored in memory)."""
    engine = request.app.state.engine
    return list(engine.trigger_history)[:limit]


# ─── Create ───────────────────────────────────────────────────────────────────

@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(request: Request, body: RuleCreate):
    """Add a new rule to the engine and persist to rules.json."""
    engine = request.app.state.engine

    if engine.find_rule(body.name):
        raise HTTPException(status_code=409, detail=f"Rule '{body.name}' already exists")

    rule = Rule(
        name=body.name,
        symbol=body.symbol,
        condition=body.condition,
        channel=body.channel,
        action=body.action,
        cooldown=body.cooldown,
        enabled=body.enabled,
    )
    engine.add_rule(rule)

    # If engine is running and the symbol is new, subscribe on the fly
    ib = getattr(request.app.state, "ib", None)
    if ib is not None and engine._stream is not None:
        await engine.subscribe_symbol(body.symbol)

    save_rules_to_file(engine.all_rules, RULES_FILE)
    return _to_response(rule)


# ─── Update ───────────────────────────────────────────────────────────────────

@router.put("/{name}", response_model=RuleResponse)
async def update_rule(request: Request, name: str, body: RuleUpdate):
    """Update an existing rule's fields and persist to rules.json."""
    engine = request.app.state.engine

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    if not engine.update_rule(name, **updates):
        raise HTTPException(status_code=404, detail=f"Rule '{name}' not found")

    save_rules_to_file(engine.all_rules, RULES_FILE)
    return _to_response(engine.find_rule(name))


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/{name}", status_code=204)
async def delete_rule(request: Request, name: str):
    """Remove a rule from the engine and persist to rules.json."""
    engine = request.app.state.engine

    if not engine.remove_rule(name):
        raise HTTPException(status_code=404, detail=f"Rule '{name}' not found")

    save_rules_to_file(engine.all_rules, RULES_FILE)


# ─── Test trigger (QA only) ────────────────────────────────────────────────
# Only registered when ENABLE_TEST_TRIGGER=true (.env). Lets QA pretend a
# rule's symbol just ticked at `mock_price` and runs the full trigger code
# path (condition check, cooldown, action dispatch / proposal creation) —
# the only way to exercise the proposal flow without waiting for real
# market conditions. Disabled by default so it doesn't exist in production.

if ENABLE_TEST_TRIGGER:

    @router.post("/{rule_id}/trigger-test", response_model=TriggerTestResponse)
    async def trigger_test(request: Request, rule_id: str, body: TriggerTestRequest):
        """Pretend `rule_id`'s symbol just ticked at `mock_price` and evaluate it."""
        engine = request.app.state.engine

        rule = engine.find_rule(rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

        ticker = Ticker(
            contract=None,
            # created=True bypasses Ticker.__post_init__, which otherwise
            # resets last/bid/ask/close back to NaN ("unset") regardless of
            # constructor args.
            created=True,
            last=body.mock_price,
            close=body.mock_price,
            ask=body.mock_price,
            bid=body.mock_price,
            volume=0,
        )

        matched = evaluate_condition(ticker, rule.condition)

        proposal = None
        if matched:
            if rule.is_on_cooldown():
                raise HTTPException(status_code=409, detail=f"Rule '{rule.name}' is on cooldown")

            rule.mark_triggered()
            ib = getattr(request.app.state, "ib", None)
            proposal = await execute_rule_action(rule, rule.symbol, ticker, ib)

            engine.trigger_history.appendleft({
                "timestamp": datetime.now().isoformat(),
                "rule_name": rule.name,
                "symbol": rule.symbol,
                "price": body.mock_price,
            })

        return TriggerTestResponse(
            matched=matched,
            rule_name=rule.name,
            symbol=rule.symbol,
            mock_price=body.mock_price,
            proposal=proposal,
        )
