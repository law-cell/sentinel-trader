"""
Option Pricing
==============
Premium estimation for option order proposals.
"""

from datetime import date


async def get_option_mid_price(symbol: str, right: str, strike: float, expiry_date: date) -> float:
    """
    Get the mid-price (bid+ask / 2) of an option contract from IB market data.

    TODO Sunday afternoon: implement via ib_async qualifyContracts +
    reqMktData + wait for bid+ask. For now, return a deterministic mock
    value so the proposal pipeline can be exercised end-to-end without
    depending on IB.
    """
    return 2.50
