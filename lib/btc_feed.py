# Live BTC/USDT price feed from Binance aggTrade WebSocket.

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

logger = logging.getLogger(__name__)

def _load_ws():
    """
    Dynamically resolve the correct websockets connect API.
    Supports websockets v10–v13 (async client changed in v12).
    """
    try:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed
        return connect, ConnectionClosed
    except ImportError:
        import websockets
        return websockets.connect, websockets.exceptions.ConnectionClosed

@dataclass
class _BtcPoint:
    """One BTC price observation: epoch timestamp + price in USD."""
    timestamp: float
    price: float

class BtcFeed:
    """
    Streams BTC/USDT prices from Binance aggTrade WebSocket.

    Properties
    ----------
    price           Latest trade price (0.0 if not connected yet).
    is_connected    WebSocket connection status.
    has_data        True once at least one price has been received.

    Methods
    -------
    momentum(seconds)    Fractional return over the last window
                         (e.g. +0.002 = BTC up 0.2%).  None if not enough history.
    volatility(seconds)  (high − low) / price over the window.
    history_seconds()    How many seconds of price history are held.
    """

    BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
    RECONNECT_INTERVAL = 5.0  # Seconds to wait before reconnecting

    def __init__(self, max_history: int = 1200):
        # max_history=1200 trades ≈ 2-3 minutes of BTC ticks at normal volume
        self._history: Deque[_BtcPoint] = deque(maxlen=max_history)
        self._price: float = 0.0
        self._connected = False
        self._running = False
        self._ws_connect, self._conn_closed = _load_ws()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def price(self) -> float:
        """Latest BTC price in USD (0.0 before any data)."""
        return self._price

    @property
    def is_connected(self) -> bool:
        """True while the Binance WebSocket is open."""
        return self._connected

    @property
    def has_data(self) -> bool:
        """True once at least one trade price has been received."""
        return self._price > 0

    # ── Signal helpers ────────────────────────────────────────────────────────

    def momentum(self, seconds: float = 30.0) -> Optional[float]:
        """
        Fractional return over the last `seconds` of history.
        Positive → BTC rising, negative → BTC falling.
        Returns None if there is not enough history yet.
        """
        if not self._history or self._price == 0:
            return None
        now = time.time()
        cutoff = now - seconds
        old_price: Optional[float] = None
        for pt in self._history:
            if pt.timestamp >= cutoff:
                old_price = pt.price
                break
        if old_price is None or old_price == 0:
            return None
        return (self._price - old_price) / old_price

    def volatility(self, seconds: float = 60.0) -> float:
        """
        Relative price range (high − low) / current_price over the last `seconds`.
        Returns 0.0 if there is not enough history.
        """
        if not self._history or self._price == 0:
            return 0.0
        now = time.time()
        cutoff = now - seconds
        prices = [pt.price for pt in self._history if pt.timestamp >= cutoff]
        if len(prices) < 2:
            return 0.0
        return (max(prices) - min(prices)) / self._price

    def history_seconds(self) -> float:
        """Span (in seconds) of the price history currently held."""
        if len(self._history) < 2:
            return 0.0
        return self._history[-1].timestamp - self._history[0].timestamp

    # ── Async lifecycle ───────────────────────────────────────────────────────

    async def run(self, auto_reconnect: bool = True) -> None:
        """Connect to Binance, stream prices, reconnect on drop."""
        import asyncio
        self._running = True
        while self._running:
            try:
                async with self._ws_connect(self.BINANCE_WS) as ws:
                    self._connected = True
                    logger.info("BtcFeed connected to Binance")
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            price = float(msg["p"])  # "p" = price in aggTrade
                            self._price = price
                            self._history.append(
                                _BtcPoint(timestamp=time.time(), price=price)
                            )
                        except (KeyError, ValueError):
                            pass  # Malformed message — skip silently
            except self._conn_closed:
                pass  # Normal disconnect — retry below
            except Exception as e:
                logger.warning(f"BtcFeed error: {e}")
            finally:
                self._connected = False

            if not self._running:
                break
            if auto_reconnect:
                logger.info(f"BtcFeed reconnecting in {self.RECONNECT_INTERVAL}s…")
                await asyncio.sleep(self.RECONNECT_INTERVAL)
            else:
                break

    async def stop(self) -> None:
        """Signal the run loop to exit."""
        self._running = False
