"""
Rule Loader
===========
Loads Rule definitions from a JSON file.

Expected JSON format — array of rule objects:

[
  {
    "name":     "NVDA Price Alert",
    "symbol":   "NVDA",
    "condition": {"type": "price_above", "threshold": 150.0},
    "action":   "console",
    "cooldown": 300,
    "enabled":  true
  },
  ...
]

All fields except "enabled" are required.
"enabled" defaults to true if omitted.
"""

import json
from pathlib import Path
from loguru import logger
from src.rules.models import Rule


def load_rules_from_file(path: str | Path) -> list[Rule]:
    """
    Parse a JSON rules file and return a list of Rule objects.

    Args:
        path: Path to the JSON file (absolute or relative to cwd)

    Returns:
        List of Rule instances. Malformed entries are skipped with a warning.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError(f"Rules file must contain a JSON array, got {type(raw).__name__}")

    rules: list[Rule] = []
    for i, entry in enumerate(raw):
        try:
            rule = Rule(
                name=entry["name"],
                symbol=entry["symbol"],
                condition=entry["condition"],
                action=entry["action"],
                cooldown=int(entry["cooldown"]),
                enabled=entry.get("enabled", True),
            )
            rules.append(rule)
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping rule at index {i} — missing or invalid field: {e}")

    logger.info(f"Loaded {len(rules)} rule(s) from {path}")
    return rules


def save_rules_to_file(rules: list[Rule], path: str | Path) -> None:
    """
    Persist a list of Rule objects back to a JSON file.
    Runtime-only state (last_triggered) is not saved.
    """
    path = Path(path)
    data = [
        {
            "name": rule.name,
            "symbol": rule.symbol,
            "condition": rule.condition,
            "action": rule.action,
            "cooldown": rule.cooldown,
            "enabled": rule.enabled,
        }
        for rule in rules
    ]
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved {len(rules)} rule(s) to {path}")
