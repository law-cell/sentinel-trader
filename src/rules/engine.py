"""
Rule Engine
===========
Subscribes to live market data and evaluates trading rules in real-time.

Usage:
    python -m src.rules.engine
    python -m src.rules.engine --rules path/to/rules.json --symbols NVDA SPY
"""

import asyncio
import argparse
import math
from collections import deque
from datetime import datetime
from pathlib import Path
from ib_async import IB, Ticker
from loguru import logger

from src.core.connection import IBConnection
from src.data.market_data import MarketDataStream
from src.rules.models import Rule
from src.rules.conditions import evaluate_condition
from src.rules.actions import execute_action
from src.rules.loader import load_rules_from_file


class RuleEngine:
    """
    Evaluates a set of trading rules against live ib_async market data.

    Workflow:
        1. Load rules via load_rules() or add_rule()
        2. Call run(ib, symbols) to subscribe to market data and start evaluation
        3. When a rule's condition is met and it's not on cooldown, its action fires
    """

    def __init__(self):
        self._rules: dict[str, list[Rule]] = {}
        self._stream: MarketDataStream | None = None
        # Ring buffer — last 100 trigger events, newest first
        self.trigger_history: deque = deque(maxlen=100)

    # ─── Rule management ─────────────────────────────────────────────────────

    def load_rules(self, path: str | Path) -> None:
        """Load rules from a JSON file, merging with any existing rules."""
        rules = load_rules_from_file(path)
        for rule in rules:
            self.add_rule(rule)

    def add_rule(self, rule: Rule) -> None:
        """Add a single rule to the engine."""
        self._rules.setdefault(rule.symbol, []).append(rule)
        logger.debug(f"Added rule '{rule.name}' for {rule.symbol}")

    def find_rule(self, name: str) -> Rule | None:
        """Return the Rule with the given name, or None if not found."""
        for rules in self._rules.values():
            for rule in rules:
                if rule.name == name:
                    return rule
        return None

    def remove_rule(self, name: str) -> bool:
        """Remove the rule with the given name. Returns True if removed."""
        for symbol, rules in list(self._rules.items()):
            for i, rule in enumerate(rules):
                if rule.name == name:
                    rules.pop(i)
                    if not rules:
                        del self._rules[symbol]
                    logger.info(f"Removed rule '{name}'")
                    return True
        return False

    def update_rule(self, name: str, **kwargs) -> bool:
        """Update fields of an existing rule in-place. Returns True if found."""
        rule = self.find_rule(name)
        if rule is None:
            return False
        for key, value in kwargs.items():
            if value is not None and hasattr(rule, key):
                setattr(rule, key, value)
        logger.info(f"Updated rule '{name}': {kwargs}")
        return True

    @property
    def all_rules(self) -> list[Rule]:
        return [r for rules in self._rules.values() for r in rules]

    @property
    def symbols(self) -> list[str]:
        return list(self._rules.keys())

    # ─── Market data access ───────────────────────────────────────────────────

    def get_ticker(self, symbol: str) -> Ticker | None:
        """Return the live Ticker for a subscribed symbol, or None."""
        if self._stream is None:
            return None
        return self._stream.subscriptions.get(symbol)

    async def subscribe_symbol(self, symbol: str) -> None:
        """Subscribe to a new symbol at runtime (after engine.run() is started)."""
        if self._stream is None:
            logger.warning("Engine not running — cannot subscribe dynamically")
            return
        if symbol not in self._stream.subscriptions:
            await self._stream.subscribe([symbol])

    # ─── Evaluation ──────────────────────────────────────────────────────────

    def evaluate(self, symbol: str, ticker: Ticker) -> None:
        """
        Evaluate all rules for a given symbol against the latest Ticker data.
        Fires the action and records to trigger_history if conditions are met.
        """
        rules = self._rules.get(symbol, [])
        for rule in rules:
            if not rule.enabled:
                continue
            if rule.is_on_cooldown():
                logger.debug(f"Rule '{rule.name}' is on cooldown — skipping")
                continue

            if evaluate_condition(ticker, rule.condition):
                logger.success(f"Rule '{rule.name}' triggered for {symbol}")
                rule.mark_triggered()
                execute_action(rule.action, rule.name, symbol, ticker)

                raw = ticker.last or ticker.close
                price = float(raw) if raw and not math.isnan(float(raw)) else 0.0
                self.trigger_history.appendleft({
                    "timestamp": datetime.now().isoformat(),
                    "rule_name": rule.name,
                    "symbol": symbol,
                    "price": price,
                })

    # ─── Main loop ───────────────────────────────────────────────────────────

    async def run(self, ib: IB, symbols: list[str]) -> None:
        """
        Subscribe to market data for the given symbols and evaluate rules
        on every incoming tick until cancelled.
        """
        active_symbols = [s for s in symbols if s in self._rules]
        if not active_symbols:
            logger.warning("No rules defined for any of the requested symbols — nothing to do")
            return

        logger.info(f"Starting rule engine for symbols: {active_symbols}")
        logger.info(f"Active rules: {len(self.all_rules)}")

        stream = MarketDataStream(ib)
        await stream.subscribe(active_symbols)
        self._stream = stream

        await asyncio.sleep(2)

        def on_pending_tickers(tickers: set[Ticker]):
            for ticker in tickers:
                symbol = ticker.contract.symbol if ticker.contract else None
                if symbol and symbol in self._rules:
                    self.evaluate(symbol, ticker)

        ib.pendingTickersEvent += on_pending_tickers
        logger.info("Rule engine running — press Ctrl+C to stop")

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            ib.pendingTickersEvent -= on_pending_tickers
            stream.unsubscribe_all()
            self._stream = None
            logger.info("Rule engine stopped")


# ─── Standalone runner ────────────────────────────────────────────────────────

async def main(rules_path: str, symbols: list[str]):
    rules_file = Path(rules_path)
    if not rules_file.exists():
        logger.error(f"Rules file not found: {rules_file}")
        return

    engine = RuleEngine()
    engine.load_rules(rules_file)

    if not engine.all_rules:
        logger.error("No valid rules loaded — exiting")
        return

    watch = symbols if symbols else engine.symbols
    logger.info(f"Watching: {watch}")

    conn = IBConnection()
    try:
        ib = await conn.connect()
        ib.reqMarketDataType(1)
        await engine.run(ib, watch)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Engine error: {e}")
    finally:
        conn.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IB Rule Engine")
    parser.add_argument("--rules", default="rules.json",
                        help="Path to rules JSON file (default: rules.json)")
    parser.add_argument("--symbols", nargs="*", default=[],
                        help="Symbols to watch (default: all symbols in rules)")
    args = parser.parse_args()
    asyncio.run(main(args.rules, args.symbols))
