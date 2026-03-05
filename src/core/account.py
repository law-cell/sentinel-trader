"""
Account Data
=============
Fetches account summary, positions, and P&L from IB.

Usage:
    python -m src.core.account
"""

import asyncio
from ib_async import IB, util
from loguru import logger
from src.core.connection import IBConnection


async def get_account_summary(ib: IB) -> dict:
    """
    Get key account metrics: net liquidation, available funds, etc.
    Returns a dict like: {"NetLiquidation": "123456.78", "AvailableFunds": "100000.00", ...}
    """
    account = ib.managedAccounts()[0]
    summary = await ib.accountSummaryAsync()

    result = {}
    for item in summary:
        if item.account == account:
            result[item.tag] = item.value

    return result


async def get_positions(ib: IB) -> list[dict]:
    """
    Get all current positions with P&L.
    Returns a list of dicts with symbol, position size, avg cost, market value, unrealized PnL.
    """
    positions = ib.positions()

    result = []
    for pos in positions:
        result.append({
            "symbol": pos.contract.symbol,
            "sec_type": pos.contract.secType,  # STK, OPT, etc.
            "exchange": pos.contract.exchange,
            "position": pos.position,           # positive=long, negative=short
            "avg_cost": pos.avgCost,
            "contract": pos.contract,           # keep full contract for later use
        })

    return result


async def get_pnl(ib: IB) -> dict:
    """
    Get real-time P&L for the account.
    Returns dict with daily PnL, unrealized PnL, realized PnL.
    """
    account = ib.managedAccounts()[0]
    pnl = ib.reqPnL(account)

    # Give it a moment to populate
    await asyncio.sleep(1)

    return {
        "daily_pnl": pnl.dailyPnL,
        "unrealized_pnl": pnl.unrealizedPnL,
        "realized_pnl": pnl.realizedPnL,
    }


def print_account_summary(summary: dict):
    """Pretty print the key account metrics."""
    key_fields = [
        "NetLiquidation",
        "TotalCashValue",
        "AvailableFunds",
        "BuyingPower",
        "GrossPositionValue",
        "MaintMarginReq",
        "UnrealizedPnL",
        "RealizedPnL",
    ]

    logger.info("=" * 50)
    logger.info("         ACCOUNT SUMMARY")
    logger.info("=" * 50)
    for field in key_fields:
        if field in summary:
            value = summary[field]
            try:
                value = f"${float(value):,.2f}"
            except (ValueError, TypeError):
                pass
            logger.info(f"  {field:<25} {value}")
    logger.info("=" * 50)


def print_positions(positions: list[dict]):
    """Pretty print current positions."""
    if not positions:
        logger.info("No open positions.")
        return

    logger.info("=" * 60)
    logger.info("         CURRENT POSITIONS")
    logger.info("=" * 60)
    logger.info(f"  {'Symbol':<10} {'Type':<6} {'Qty':>8} {'Avg Cost':>12}")
    logger.info("-" * 60)
    for pos in positions:
        logger.info(
            f"  {pos['symbol']:<10} {pos['sec_type']:<6} "
            f"{pos['position']:>8.0f} {pos['avg_cost']:>12.2f}"
        )
    logger.info("=" * 60)


# ─── Run ─────────────────────────────────────────────────────────

async def main():
    conn = IBConnection()

    try:
        ib = await conn.connect()

        # Account Summary
        summary = await get_account_summary(ib)
        print_account_summary(summary)

        # Positions
        positions = await get_positions(ib)
        print_positions(positions)

        # P&L
        pnl = await get_pnl(ib)
        logger.info(f"Daily P&L: ${pnl['daily_pnl']:,.2f}" if pnl['daily_pnl'] else "Daily P&L: N/A")
        logger.info(f"Unrealized P&L: ${pnl['unrealized_pnl']:,.2f}" if pnl['unrealized_pnl'] else "Unrealized P&L: N/A")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        conn.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
