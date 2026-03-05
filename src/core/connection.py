"""
IB Connection Manager
=====================
Handles connecting to TWS/IB Gateway, with auto-reconnect support.

Usage:
    python -m src.core.connection

Make sure TWS or IB Gateway is running with Paper Account before executing.
"""

import asyncio
from ib_async import IB, util
from loguru import logger
from src.config.settings import IB_HOST, IB_PORT, IB_CLIENT_ID


class IBConnection:
    """
    Manages a single connection to IB TWS/Gateway.

    Wraps ib_async.IB with:
    - Centralized config
    - Auto-reconnect on disconnect
    - Clean shutdown
    - Event logging
    """

    def __init__(self, host: str = IB_HOST, port: int = IB_PORT, client_id: int = IB_CLIENT_ID):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()

        # Register event handlers
        self.ib.connectedEvent += self._on_connected
        self.ib.disconnectedEvent += self._on_disconnected
        self.ib.errorEvent += self._on_error

    async def connect(self) -> IB:
        """Connect to IB TWS/Gateway. Returns the IB instance."""
        logger.info(f"Connecting to IB at {self.host}:{self.port} (clientId={self.client_id})...")
        try:
            await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
            return self.ib
        except ConnectionRefusedError:
            logger.error(
                "Connection refused. Make sure TWS or IB Gateway is running "
                "and API connections are enabled."
            )
            raise
        except asyncio.TimeoutError:
            logger.error("Connection timed out. Check your host/port settings.")
            raise

    def disconnect(self):
        """Gracefully disconnect from IB."""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB.")

    def is_connected(self) -> bool:
        return self.ib.isConnected()

    # ─── Event Handlers ─────────────────────────────────────────

    def _on_connected(self):
        logger.success(f"Connected to IB at {self.host}:{self.port}")

    def _on_disconnected(self):
        logger.warning("Disconnected from IB.")

    def _on_error(self, req_id: int, error_code: int, error_string: str, contract):
        # Filter out non-critical "system" messages (codes 2103-2108 are info messages)
        if 2100 <= error_code <= 2200:
            logger.debug(f"IB Info [{error_code}]: {error_string}")
        else:
            logger.error(f"IB Error [{error_code}] (reqId={req_id}): {error_string}")


# ─── Quick Test ──────────────────────────────────────────────────

async def main():
    """Quick connection test. Run this file directly to verify IB is reachable."""
    conn = IBConnection()

    try:
        ib = await conn.connect()

        # Basic connection info
        accounts = ib.managedAccounts()
        logger.info(f"Managed accounts: {accounts}")

        server_time = await ib.reqCurrentTimeAsync()
        logger.info(f"IB Server time: {server_time}")

        logger.success("Connection test passed! Your IB setup is working.")

    except Exception as e:
        logger.error(f"Connection test failed: {e}")
    finally:
        conn.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
