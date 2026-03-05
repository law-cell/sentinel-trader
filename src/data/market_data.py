"""
Real-Time Market Data
=====================
Subscribe to live streaming quotes for stocks and ETFs.
This is the foundation for the rule engine - it receives price updates
that will later trigger trading rules.

Usage:
    python -m src.data.market_data
"""

import asyncio
from datetime import datetime
from ib_async import IB, Stock, Ticker, util
from loguru import logger
from src.core.connection import IBConnection
from src.config.settings import WATCHLIST


class MarketDataStream:
    """
    Manages real-time market data subscriptions.

    Subscribes to streaming quotes and invokes callbacks on price updates.
    This will later feed into the rule engine.
    """

    def __init__(self, ib: IB):
        self.ib = ib
        self.subscriptions: dict[str, Ticker] = {}  # symbol -> Ticker

    async def subscribe(self, symbols: list[str]) -> dict[str, Ticker]:
        """
        Subscribe to real-time quotes for a list of stock symbols.
        Returns dict of symbol -> Ticker objects that update in real-time.
        """
        contracts = []
        for symbol in symbols:
            contract = Stock(symbol, "SMART", "USD")
            contracts.append(contract)

        # Qualify contracts first (fills in conId, primaryExchange, etc.)
        qualified = await self.ib.qualifyContractsAsync(*contracts)
        logger.info(f"Qualified {len(qualified)} contracts")

        # Subscribe to market data
        for contract in qualified:
            ticker = self.ib.reqMktData(contract, genericTickList="", snapshot=False)
            self.subscriptions[contract.symbol] = ticker
            logger.info(f"Subscribed to {contract.symbol} ({contract.primaryExchange})")

        return self.subscriptions

    def unsubscribe_all(self):
        """Cancel all market data subscriptions."""
        for symbol, ticker in self.subscriptions.items():
            self.ib.cancelMktData(ticker.contract)
            logger.info(f"Unsubscribed from {symbol}")
        self.subscriptions.clear()

    def get_snapshot(self) -> list[dict]:
        """
        Get current snapshot of all subscribed tickers.
        Returns list of dicts with latest bid/ask/last/volume.
        """
        result = []
        for symbol, ticker in self.subscriptions.items():
            result.append({
                "symbol": symbol,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "last": ticker.last,
                "volume": ticker.volume,
                "high": ticker.high,
                "low": ticker.low,
                "close": ticker.close,  # previous close
                "time": datetime.now().strftime("%H:%M:%S"),
            })
        return result


def print_quotes(snapshots: list[dict]):
    """Pretty print current quotes."""
    logger.info("=" * 80)
    logger.info(f"  {'Symbol':<8} {'Bid':>10} {'Ask':>10} {'Last':>10} {'Volume':>12} {'Time':<10}")
    logger.info("-" * 80)
    for s in snapshots:
        bid = f"{s['bid']:.2f}" if s['bid'] and s['bid'] > 0 else "---"
        ask = f"{s['ask']:.2f}" if s['ask'] and s['ask'] > 0 else "---"
        last = f"{s['last']:.2f}" if s['last'] and s['last'] > 0 else "---"
        vol = f"{s['volume']:,.0f}" if s['volume'] and s['volume'] > 0 else "---"
        logger.info(f"  {s['symbol']:<8} {bid:>10} {ask:>10} {last:>10} {vol:>12} {s['time']:<10}")
    logger.info("=" * 80)


# ─── Run ─────────────────────────────────────────────────────────

async def main():
    """
    Subscribe to watchlist and print live quotes every 3 seconds for 30 seconds.
    This demonstrates the real-time data feed is working.
    """
    conn = IBConnection()

    try:
        ib = await conn.connect()

        # Use delayed data if you don't have a market data subscription
        # Comment out the next line if you have real-time data
        ib.reqMarketDataType(3)  # 3 = Delayed, 1 = Real-time

        stream = MarketDataStream(ib)
        await stream.subscribe(WATCHLIST)

        # Wait a bit for initial data to arrive
        logger.info("Waiting for market data...")
        await asyncio.sleep(3)

        # Print quotes every 3 seconds for 30 seconds
        for i in range(10):
            snapshots = stream.get_snapshot()
            print_quotes(snapshots)
            await asyncio.sleep(3)

        stream.unsubscribe_all()

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        conn.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
