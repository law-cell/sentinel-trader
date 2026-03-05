"""
Options Chain Data
==================
Fetches option chains with Greeks for a given underlying stock.

Usage:
    python -m src.data.options
    python -m src.data.options TSLA
"""

import sys
import asyncio
from datetime import datetime
from ib_async import IB, Stock, Option, util
from loguru import logger
from src.core.connection import IBConnection


async def get_option_chains(ib: IB, symbol: str) -> dict:
    """
    Get all available option expirations and strikes for a symbol.
    """
    stock = Stock(symbol, "SMART", "USD")
    await ib.qualifyContractsAsync(stock)

    chains = await ib.reqSecDefOptParamsAsync(
        stock.symbol, "", stock.secType, stock.conId
    )

    if not chains:
        logger.warning(f"No option chains found for {symbol}")
        return {}

    chain = next((c for c in chains if c.exchange == "SMART"), chains[0])

    # Filter out today and past expirations
    today = datetime.now().strftime("%Y%m%d")
    future_exps = [exp for exp in sorted(chain.expirations) if exp > today]

    return {
        "symbol": symbol,
        "exchange": chain.exchange,
        "expirations": future_exps,
        "strikes": sorted(chain.strikes),
        "multiplier": chain.multiplier,
    }


async def get_option_quotes(
    ib: IB,
    symbol: str,
    expiration: str,
    strikes: list[float],
    right: str = "C",
) -> list[dict]:
    """
    Get live quotes and Greeks for specific option contracts.
    """
    contracts = []
    for strike in strikes:
        opt = Option(symbol, expiration, strike, right, "SMART")
        contracts.append(opt)

    # Qualify in batch - some may fail, filter them out
    qualified = await ib.qualifyContractsAsync(*contracts)
    valid_contracts = [c for c in qualified if c is not None and c.conId > 0]

    if not valid_contracts:
        logger.warning(f"No valid option contracts found for {symbol} {expiration} {right}")
        return []

    logger.info(f"Qualified {len(valid_contracts)} / {len(contracts)} option contracts")

    # Request market data for valid contracts only
    tickers = []
    for contract in valid_contracts:
        ticker = ib.reqMktData(contract, genericTickList="106", snapshot=False)
        tickers.append(ticker)

    # Wait for data to populate
    logger.info("Waiting for option data to arrive...")
    await asyncio.sleep(5)

    results = []
    for ticker in tickers:
        contract = ticker.contract
        greeks = ticker.modelGreeks

        result = {
            "strike": contract.strike,
            "right": contract.right,
            "expiration": contract.lastTradeDateOrContractMonth,
            "bid": ticker.bid if ticker.bid and ticker.bid > 0 else None,
            "ask": ticker.ask if ticker.ask and ticker.ask > 0 else None,
            "last": ticker.last if ticker.last and ticker.last > 0 else None,
            "volume": ticker.volume if ticker.volume and ticker.volume > 0 else 0,
        }

        if greeks:
            result.update({
                "implied_vol": round(greeks.impliedVol, 4) if greeks.impliedVol else None,
                "delta": round(greeks.delta, 4) if greeks.delta else None,
                "gamma": round(greeks.gamma, 6) if greeks.gamma else None,
                "theta": round(greeks.theta, 4) if greeks.theta else None,
                "vega": round(greeks.vega, 4) if greeks.vega else None,
            })
        else:
            result.update({
                "implied_vol": None, "delta": None, "gamma": None,
                "theta": None, "vega": None,
            })

        results.append(result)

    # Cancel market data
    for ticker in tickers:
        ib.cancelMktData(ticker.contract)

    return results


def print_chain_info(chain: dict):
    """Print option chain overview."""
    if not chain:
        return

    exps = chain["expirations"]
    strikes = chain["strikes"]

    logger.info("=" * 60)
    logger.info(f"  Option Chain: {chain['symbol']}")
    logger.info(f"  Exchange: {chain['exchange']}")
    logger.info(f"  Multiplier: {chain['multiplier']}")
    logger.info(f"  Expirations: {len(exps)} available (future only)")
    logger.info(f"    Nearest: {exps[:5]}")
    logger.info(f"    Furthest: {exps[-3:]}")
    logger.info(f"  Strikes: {len(strikes)} available ({strikes[0]} - {strikes[-1]})")
    logger.info("=" * 60)


def print_option_quotes(quotes: list[dict]):
    """Pretty print option quotes with Greeks."""
    if not quotes:
        logger.info("No option data available.")
        return

    right_label = "CALLS" if quotes[0]["right"] == "C" else "PUTS"
    logger.info("=" * 90)
    logger.info(f"  {right_label} - Exp: {quotes[0]['expiration']}")
    logger.info(f"  {'Strike':>8} {'Bid':>8} {'Ask':>8} {'Last':>8} {'IV':>8} {'Delta':>8} {'Theta':>8} {'Vega':>8}")
    logger.info("-" * 90)

    for q in quotes:
        bid = f"{q['bid']:.2f}" if q['bid'] else "---"
        ask = f"{q['ask']:.2f}" if q['ask'] else "---"
        last = f"{q['last']:.2f}" if q['last'] else "---"
        iv = f"{q['implied_vol']:.2%}" if q['implied_vol'] else "---"
        delta = f"{q['delta']:.3f}" if q['delta'] else "---"
        theta = f"{q['theta']:.3f}" if q['theta'] else "---"
        vega = f"{q['vega']:.3f}" if q['vega'] else "---"

        logger.info(
            f"  {q['strike']:>8.1f} {bid:>8} {ask:>8} {last:>8} "
            f"{iv:>8} {delta:>8} {theta:>8} {vega:>8}"
        )
    logger.info("=" * 90)


# ─── Run ─────────────────────────────────────────────────────────

async def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NVDA"

    conn = IBConnection()

    try:
        ib = await conn.connect()
        ib.reqMarketDataType(3)

        # Step 1: Get available chains
        chain = await get_option_chains(ib, symbol)
        print_chain_info(chain)

        if not chain or not chain["expirations"]:
            logger.error("No future expirations available.")
            return

        # Step 2: Pick the nearest FUTURE expiration
        nearest_exp = chain["expirations"][0]
        logger.info(f"Using nearest expiration: {nearest_exp}")

        # Step 3: Get current stock price
        stock = Stock(symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(stock)
        ticker = ib.reqMktData(stock, snapshot=False)
        await asyncio.sleep(2)

        current_price = ticker.last or ticker.close or 100
        ib.cancelMktData(stock)
        logger.info(f"Current {symbol} price: ${current_price:.2f}")

        # Step 4: Select 5 strikes closest to current price
        # Only pick strikes that are round numbers (more likely to have contracts)
        all_strikes = sorted(chain["strikes"])
        atm_strikes = sorted(all_strikes, key=lambda s: abs(s - current_price))[:7]
        atm_strikes = sorted(atm_strikes)
        logger.info(f"Selected strikes: {atm_strikes}")

        # Step 5: Get call quotes
        call_quotes = await get_option_quotes(ib, symbol, nearest_exp, atm_strikes, right="C")
        print_option_quotes(call_quotes)

        # Step 6: Get put quotes
        put_quotes = await get_option_quotes(ib, symbol, nearest_exp, atm_strikes, right="P")
        print_option_quotes(put_quotes)

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
