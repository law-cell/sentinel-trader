"""
Rule Safety Validator
=====================
Checks an LLM-extracted Rule against the hardcoded safety policy in
src/config/settings.py before it is allowed to be saved.

Returns a list of human-readable error strings — empty means valid.
"""

from src.config.settings import ALLOWED_SYMBOLS, MAX_OPTION_EXPIRY_DAYS, OPTION_SIDE_ALLOWED
from src.rules.models import Rule, OptionOrderAction, StockOrderAction


def validate_rule(rule: Rule) -> list[str]:
    errors: list[str] = []

    if rule.symbol not in ALLOWED_SYMBOLS:
        errors.append(
            f"Symbol '{rule.symbol}' is not in the allowed symbol list: "
            f"{sorted(ALLOWED_SYMBOLS)}"
        )

    if rule.cooldown < 60:
        errors.append(f"cooldown must be at least 60 seconds, got {rule.cooldown}")

    action = rule.action
    if isinstance(action, OptionOrderAction):
        if action.expiry_days > MAX_OPTION_EXPIRY_DAYS:
            errors.append(
                f"expiry_days must be at most {MAX_OPTION_EXPIRY_DAYS}, "
                f"got {action.expiry_days}"
            )
        # Defense-in-depth: OptionOrderAction has no `side` field, so the LLM
        # cannot request anything other than the policy-forced side. This
        # check guards against future schema changes re-introducing one.
        if "SELL" not in OPTION_SIDE_ALLOWED:
            errors.append("Option orders are not permitted by current safety policy")

    elif isinstance(action, StockOrderAction):
        if action.order_type == "LIMIT" and action.limit_price is None:
            errors.append("limit_price is required when order_type is 'LIMIT'")

    return errors
