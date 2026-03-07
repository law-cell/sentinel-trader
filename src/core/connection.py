"""
IB Connection Manager
=====================
Handles connecting to TWS/IB Gateway, with auto-reconnect support.

Usage:
    python -m src.core.connection

Make sure TWS or IB Gateway is running with Paper Account before executing.
"""

import asyncio
from typing import Callable, Awaitable
from ib_async import IB, util
from loguru import logger
from src.config.settings import IB_HOST, IB_PORT, IB_CLIENT_ID

RECONNECT_INTERVAL = 10  # seconds between reconnect attempts


class IBConnection:
    """
    Manages a single connection to IB TWS/Gateway.

    Wraps ib_async.IB with:
    - Centralized config
    - Auto-reconnect on disconnect (every RECONNECT_INTERVAL seconds)
    - Reconnect callback to restore subscriptions and data types
    - Clean shutdown
    - Event logging
    """

    def __init__(self, host: str = IB_HOST, port: int = IB_PORT, client_id: int = IB_CLIENT_ID):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()

        self._shutdown = False
        self._reconnect_task: asyncio.Task | None = None
        # Called with (ib) after a successful reconnect; set via set_reconnect_callback()
        self._reconnect_callback: Callable[[IB], Awaitable[None]] | None = None

        self.ib.connectedEvent += self._on_connected
        self.ib.disconnectedEvent += self._on_disconnected
        self.ib.errorEvent += self._on_error

    def set_reconnect_callback(self, callback: Callable[[IB], Awaitable[None]]) -> None:
        """Register an async callback to run after each successful reconnect."""
        self._reconnect_callback = callback

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
        """Gracefully disconnect and stop the reconnect loop."""
        self._shutdown = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB.")

    def is_connected(self) -> bool:
        return self.ib.isConnected()

    # ─── Reconnect loop ──────────────────────────────────────────

    async def _reconnect_loop(self) -> None:
        """Attempt to reconnect every RECONNECT_INTERVAL seconds until successful."""
        attempt = 0
        while not self._shutdown:
            await asyncio.sleep(RECONNECT_INTERVAL)
            if self._shutdown or self.ib.isConnected():
                return
            attempt += 1
            logger.info(f"Reconnect attempt #{attempt}...")
            try:
                await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
                logger.success("Reconnected to IB")
                if self._reconnect_callback:
                    await self._reconnect_callback(self.ib)
                return  # success — loop exits; a new loop starts on next disconnect
            except Exception as e:
                logger.warning(f"Reconnect failed: {e} — retrying in {RECONNECT_INTERVAL}s")

    # ─── Event Handlers ─────────────────────────────────────────

    def _on_connected(self):
        logger.success(f"Connected to IB at {self.host}:{self.port}")

    def _on_disconnected(self):
        logger.warning("Disconnected from IB.")
        if not self._shutdown:
            # Schedule reconnect loop as a new asyncio task
            loop = asyncio.get_event_loop()
            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = loop.create_task(self._reconnect_loop())
                logger.info(f"Reconnect loop started — will retry every {RECONNECT_INTERVAL}s")

    def _on_error(self, req_id: int, error_code: int, error_string: str, contract):
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
