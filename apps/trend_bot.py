"""
Automated Polymarket Trend-Following Bot
==============================================================

Run:
    python apps/trend_bot.py --paper          # paper trade (safe)
    python apps/trend_bot.py                  # live mode (real USDC)

Environment variables (add to .env):
    POLY_PRIVATE_KEY=0x...
    POLY_SAFE_ADDRESS=0x...

Optional for gasless trading:
    POLY_BUILDER_API_KEY=...
    POLY_BUILDER_API_SECRET=...
    POLY_BUILDER_API_PASSPHRASE=...

"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import argparse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from dotenv import load_dotenv
load_dotenv()

# ── Project imports ───────────────────────────────────────────────────────────
from src.config import Config
from src.bot import TradingBot
from lib.display import Display
from lib.market_manager import MarketManager
from lib.position_manager import PositionManager, Position
from lib.price_tracker import PriceTracker
from lib.console import Colors, LogBuffer
from lib.bot_stats import BotStats
from lib.btc_feed import BtcFeed

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("trend_bot")

# ── Trade file logger ─────────────────────────────────────────────────────────
trade_logger = logging.getLogger("trade_logger")
trade_logger.setLevel(logging.INFO)
_trade_handler = logging.FileHandler("trade_log.jsonl", mode="a")
_trade_handler.setFormatter(logging.Formatter("%(message)s"))  # raw JSON only
trade_logger.addHandler(_trade_handler)
trade_logger.propagate = False  # don't leak into root logger


def _log(record: dict) -> None:
    """Stamp a record with ISO timestamp and write one JSON line."""
    record["ts"] = datetime.now().isoformat(timespec="milliseconds")
    trade_logger.info(json.dumps(record))

# =============================================================================
#  CONFIG — all tunable parameters
# =============================================================================

# ── Strategy parameters ───────────────────────────────────────────────────────
LOOKBACK_SECONDS  = 45.0    # How far back (s) to look when computing the trend
MIN_SAMPLES       = 2       # Minimum price points required before signalling
TREND_THRESHOLD   = 0.30    # Minimum R² score (0–1); higher = cleaner trend required
MIN_PRICE_CHANGE  = 0.0005  # Minimum avg per-sample move to ignore noise

# ── Risk controls ─────────────────────────────────────────────────────────────
TAKE_PROFIT   = 0.10   # Close trade when price rises this much above entry (USDC)
STOP_LOSS     = 0.10    # Close trade when price falls this much below entry (USDC)
MIN_SPREAD    = 0.04    # Skip entry if bid-ask spread is wider than this
COOLDOWN      = 1.0    # Minimum seconds between consecutive entries
MIN_HOLD_TIME = 1.0    # SL cannot fire before this many seconds in a position
MAX_POSITIONS = 5       # Maximum concurrent open positions

# ── Trade sizing ──────────────────────────────────────────────────────────────
SIZE_USDC = 1000.0         # USDC to spend per trade

# ── Bot settings ──────────────────────────────────────────────────────────────
COIN           = "BTC"  # Coin market to trade (only BTC supported currently)
UI_REFRESH     = 0.5    # Terminal redraw interval in seconds
LOG_BUFFER_SIZE = 8     # Number of recent log lines shown in the terminal UI

# ── Market expiry guard ───────────────────────────────────────────────────────
NO_ENTRY_AT_START = 0       # Don't enter a trade if market started less than this many seconds ago
NO_ENTRY_BEFORE_EXPIRY = 0  # Don't enter a trade if market expires within this many seconds
FORCE_EXIT_BEFORE_EXPIRY = 10  # Force-close open positions this many seconds before expiry (0 disables)

# ── Entry price safety band ───────────────────────────────────────────────────
MIN_ENTRY_PRICE = 0.01  # Avoid entering when outcome price is too close to 0
MAX_ENTRY_PRICE = 0.99  # Avoid entering when outcome price is too close to 1

@dataclass
class Signal:
    """A trading signal produced by a strategy."""

    side: str
    confidence: float
    reason: str
    slope: float = 0.0


class BaseStrategy(ABC):
    """Abstract base class for strategy implementations."""

    @abstractmethod
    def evaluate(
        self,
        up_mid: float,
        down_mid: float,
        up_bid: float,
        up_ask: float,
        down_bid: float,
        down_ask: float,
        tracker: PriceTracker,
        btc: Optional[BtcFeed] = None,
    ) -> Optional[Signal]:
        """Return a Signal to enter a trade, or None to skip this tick."""


class TrendFollowingStrategy(BaseStrategy):
    """Trend-following strategy using linear regression slope + R^2."""

    def __init__(
        self,
        lookback_seconds: float = 30.0,
        min_samples: int = 4,
        trend_threshold: float = 0.75,
        min_price_change: float = 0.001,
    ):
        self.lookback_seconds = lookback_seconds
        self.min_samples = min_samples
        self.trend_threshold = trend_threshold
        self.min_price_change = min_price_change

    def _get_recent_history(self, tracker: PriceTracker, side: str, lookback: float) -> list:
        """Return price history points from the last lookback seconds."""
        history = tracker.get_history(side)
        if not history:
            return []
        cutoff = time.time() - lookback
        return [pt for pt in history if pt.timestamp >= cutoff]

    def _is_price_safe(self, price: float) -> bool:
        """Avoid entering when outcome is near-decided (price near 0 or 1)."""
        return MIN_ENTRY_PRICE <= price <= MAX_ENTRY_PRICE

    def _regression_r2(self, history: list) -> tuple[float, float, float]:
        """Compute linear regression slope, R^2, and total price change."""
        if len(history) < 2:
            return 0.0, 0.0, 0.0

        x = [pt.timestamp for pt in history]
        y = [pt.price for pt in history]
        x0 = x[0]
        xs = [t - x0 for t in x]

        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(y) / n

        ss_xx = sum((xi - mean_x) ** 2 for xi in xs)
        ss_yy = sum((yi - mean_y) ** 2 for yi in y)
        ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(xs, y))

        if ss_xx == 0 or ss_yy == 0:
            return 0.0, 0.0, 0.0

        slope = ss_xy / ss_xx
        intercept = mean_y - slope * mean_x
        y_pred = [slope * xi + intercept for xi in xs]
        ss_res = sum((yi - ypi) ** 2 for yi, ypi in zip(y, y_pred))
        r2 = max(0.0, min(1.0, 1.0 - ss_res / ss_yy))

        return slope, r2, y[-1] - y[0]

    def evaluate(
        self,
        up_mid: float,
        down_mid: float,
        up_bid: float,
        up_ask: float,
        down_bid: float,
        down_ask: float,
        tracker: PriceTracker,
        btc: Optional[BtcFeed] = None,
    ) -> Optional[Signal]:
        """Evaluate recent trend and return a Signal or None."""
        up_history = self._get_recent_history(tracker, "up", self.lookback_seconds)
        down_history = self._get_recent_history(tracker, "down", self.lookback_seconds)

        if len(up_history) < self.min_samples and len(down_history) < self.min_samples:
            return None

        candidates: list[Signal] = []

        if len(up_history) >= self.min_samples and self._is_price_safe(up_mid):
            slope, r2, total_change = self._regression_r2(up_history)
            avg_move = abs(total_change / max(1, len(up_history) - 1))
            if slope > 0 and r2 >= self.trend_threshold and avg_move >= self.min_price_change:
                candidates.append(
                    Signal(
                        side="up",
                        confidence=r2,
                        slope=slope,
                        reason=f"UP trending up  Δ={total_change:+.4f}  R²={r2:.2f}  slope={slope:+.5f}",
                    )
                )

        if len(down_history) >= self.min_samples and self._is_price_safe(down_mid):
            slope, r2, total_change = self._regression_r2(down_history)
            avg_move = abs(total_change / max(1, len(down_history) - 1))
            if slope > 0 and r2 >= self.trend_threshold and avg_move >= self.min_price_change:
                candidates.append(
                    Signal(
                        side="down",
                        confidence=r2,
                        slope=slope,
                        reason=f"DOWN trending up  Δ={total_change:+.4f}  R²={r2:.2f}  slope={slope:+.5f}",
                    )
                )

        if not candidates:
            return None

        best = max(candidates, key=lambda s: s.confidence)

        if btc and btc.has_data:
            btc_mom = btc.momentum(self.lookback_seconds)
            if btc_mom is not None:
                agrees = (btc_mom > 0 and best.side == "up") or (btc_mom < 0 and best.side == "down")
                if not agrees:
                    return None
                best.reason += f"  BTC={btc_mom * 100:+.3f}%"

        return best

# =============================================================================
#  AutoBot 
# =============================================================================

class AutoBot: # Main bot class that encapsulates all logic and state for the trading bot.

    def __init__(
        self,
        *,
        coin: str,
        strategy: BaseStrategy,
        size_usdc: float,
        take_profit: float,
        stop_loss: float,
        max_positions: int,
        min_spread: float,
        cooldown: float,
        min_hold_time: float,
        force_exit_before: int,
        paper: bool,
        bot: Optional[TradingBot] = None,
    ):
        self.coin          = coin
        self.strategy      = strategy
        self.size_usdc     = size_usdc
        self.min_spread    = min_spread
        self.cooldown      = cooldown
        self.min_hold_time = min_hold_time
        self.force_exit_before = force_exit_before
        self.paper         = paper
        self.bot           = bot

        self.market    = MarketManager(coin=coin)
        self.tracker   = PriceTracker(lookback_seconds=60, max_history=500)
        self.positions = PositionManager()
        self.positions.take_profit = take_profit
        self.positions.stop_loss = stop_loss
        self.positions.max_positions = max_positions
        self.stats = BotStats()
        self.log   = LogBuffer(max_size=LOG_BUFFER_SIZE)
        self.btc   = BtcFeed()

        self._last_trade_time: float = 0.0
        self._running = False

    # ── Price helpers ─────────────────────────────────────────────────────────

    def _mid(self, side: str) -> float: 
        ob = self.market.get_orderbook(side)
        return ob.mid_price if ob else 0.0

    def _ask(self, side: str) -> float:
        return self.market.get_best_ask(side)

    def _spread(self, side: str) -> float:
        return self.market.get_spread(side)

    def _prices(self) -> Dict[str, float]:
        return {"up": self._mid("up"), "down": self._mid("down")}

    # ── Main lifecycle ────────────────────────────────────────────────────────

    async def run(self) -> None:
        self._running = True
        mode = "PAPER" if self.paper else "LIVE"
        self.log.add(f"AutoBot starting [{mode}] coin={self.coin}", "info")
        _log({
            "event":      "START",
            "mode":       mode,
            "coin":       self.coin,
            "strategy":   type(self.strategy).__name__,
            "size_usdc":  self.size_usdc,
            "tp":         self.positions.take_profit,
            "sl":         self.positions.stop_loss,
            "max_pos":    self.positions.max_positions,
            "min_spread": self.min_spread,
            "cooldown":   self.cooldown,
            "min_hold":   self.min_hold_time,
        })

        # ── Register market callbacks ─────────────────────────────────────────

        @self.market.on_book_update
        async def on_book(snapshot):
            if self.market.current_market:
                for side, tid in self.market.current_market.token_ids.items():
                    if tid == snapshot.asset_id:
                        self.tracker.record(side, snapshot.mid_price)
                        break

        @self.market.on_connect
        def on_connect():
            self.log.add("WebSocket connected ✓", "success")

        @self.market.on_disconnect
        def on_disconnect():
            self.log.add("WebSocket disconnected – reconnecting…", "warning")

        @self.market.on_market_change
        def on_market_change(old_slug, new_slug):
            self.log.add(f"Market rotated → {new_slug[-20:]}", "info")
            self._emergency_close_all()
            self.tracker.clear()
            self.log.add("Price history cleared for new market", "info")

        # ── Start sub-components ──────────────────────────────────────────────

        if not await self.market.start():
            self.log.add("Failed to start MarketManager!", "error")
            return

        btc_task = asyncio.create_task(self.btc.run(auto_reconnect=True))
        self.log.add("BTC feed starting…", "info")
        self.log.add(
            f"Market: {self.market.current_market.question[:50] if self.market.current_market else '?'}",
            "info",
        )

        self.log.add("Waiting for price data…", "info")
        await self.market.wait_for_data(timeout=10.0)

        # ── Main loop ─────────────────────────────────────────────────────────
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            await self.btc.stop()
            btc_task.cancel()
            try:
                await btc_task
            except asyncio.CancelledError:
                pass
            await self.market.stop()
            self.log.add("AutoBot stopped.", "info")
            _log({
                "event":         "STOP",
                "trades_placed": self.stats.trades_placed,
                "trades_closed": self.stats.trades_closed,
                "wins":          self.stats.wins,
                "losses":        self.stats.losses,
                "total_pnl":     round(self.stats.total_pnl, 4),
                "win_rate":      round(self.stats.win_rate, 1),
                "uptime":        self.stats.uptime,
            })

    # ── Tick ──────────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        prices = self._prices()
        mkt = self.market.current_market

        # 1. Check exits
        for pos, exit_type, pnl in self.positions.check_all_exits(prices):
            if exit_type == "stop_loss" and pos.get_hold_time() < self.min_hold_time:
                continue
            await self._exit_position(pos, exit_type if exit_type else "UNKNOWN", pnl)

        # 1b. Force time-based exits shortly before expiry
        if mkt and self.force_exit_before > 0 and mkt.is_ending_soon(self.force_exit_before):
            for pos in self.positions.get_all_positions():
                px = prices.get(pos.side, 0.0)
                if px <= 0:
                    continue
                pnl = pos.get_pnl(px)
                await self._exit_position(pos, f"TIME_EXIT_{self.force_exit_before}s", pnl)
            return

        # 2. Record prices into rolling history
        self.tracker.record_prices(prices)

        # 3. Guards: cooldown, capacity, live prices, market expiry
        if time.time() - self._last_trade_time < self.cooldown:
            return
        if not self.positions.can_open_position:
            return

        up_mid   = prices.get("up",   0.0)
        down_mid = prices.get("down", 0.0)
        if up_mid <= 0 or down_mid <= 0:
            return

        if mkt and (mkt.is_ending_soon(NO_ENTRY_BEFORE_EXPIRY) or mkt.is_just_started(NO_ENTRY_AT_START)):
            return

        # 4. Strategy evaluation
        signal = self.strategy.evaluate(
            up_mid, down_mid,
            self.market.get_best_bid("up"),
            self.market.get_best_ask("up"),
            self.market.get_best_bid("down"),
            self.market.get_best_ask("down"),
            self.tracker,
            btc=self.btc,
        )
        if signal is None:
            return

        # 5. Spread guard for the chosen side
        spread = self._spread(signal.side)
        if spread > self.min_spread:
            self.log.add(
                f"Skipped {signal.side.upper()} – spread {spread:.4f} > {self.min_spread}",
                "warning",
            )
            return

        # 6. Enter
        await self._enter(signal)

    # ── Enter / exit ──────────────────────────────────────────────────────────

    async def _enter(self, signal: Signal) -> None:
        entry_price = self._ask(signal.side)
        if entry_price <= 0:
            return

        size     = self.size_usdc / entry_price
        order_id: Optional[str] = None
        token_id = (
            self.market.current_market.token_ids.get(signal.side, "")
            if self.market.current_market else ""
        )

        if not self.paper and self.bot and self.market.current_market:
            if not token_id:
                reason = "Missing token_id for selected side"
                self.log.add(f"Order FAILED: {reason}", "error")
                _log({
                    "event":   "ORDER_FAILED",
                    "side":    signal.side,
                    "price":   round(entry_price, 4),
                    "size":    round(size, 2),
                    "reason":  reason,
                })
                return

            result = await self.bot.place_order(
                token_id=token_id,
                price=round(entry_price, 4),
                size=round(size, 2),
                side="BUY",
            )
            if not result.success:
                self.log.add(f"Order FAILED: {result.message}", "error")
                _log({
                    "event":   "ORDER_FAILED",
                    "side":    signal.side,
                    "price":   round(entry_price, 4),
                    "size":    round(size, 2),
                    "reason":  result.message,
                })
                return
            order_id = result.order_id

        pos = self.positions.open_position(
            side=signal.side,
            token_id=token_id,
            entry_price=entry_price,
            size=size,
            order_id=order_id,
        )
        if pos is None:
            return

        # ── Compute and store entry-context on the position ───────────────────
        mkt = self.market.current_market
        mkt_elapsed   = -1
        mkt_remaining = -1
        if mkt:
            end_ts = mkt.end_timestamp()
            if end_ts:
                mkt_remaining = max(0, int(end_ts - time.time()))
                mkt_elapsed   = max(0, 300 - mkt_remaining)

        mid_price           = self._mid(signal.side)
        spread              = self._spread(signal.side)
        slippage            = round(entry_price - mid_price, 4)

        pos.r2                    = round(signal.confidence, 4)
        pos.slope                 = round(signal.slope, 6)
        pos.spread_at_entry       = round(spread, 4)
        pos.slippage              = slippage
        pos.mkt_elapsed_at_entry  = mkt_elapsed
        pos.mkt_remaining_at_entry = mkt_remaining

        self._last_trade_time = time.time()
        self.stats.trades_placed += 1

        mode_prefix = "[PAPER] " if self.paper else ""
        if mkt_elapsed >= 0:
            em, es = divmod(mkt_elapsed, 60)
            entry_str = f"{em}:{es:02d}"
        else:
            entry_str = "?"
        self.log.add(
            f"{mode_prefix}BUY {signal.side.upper()} @ {entry_price:.4f}  "
            f"${self.size_usdc:.2f}  R²={signal.confidence:.2f}  "
            f"(Entry: {entry_str})",
            "trade",
        )
        _log({
            "event":        "ENTER",
            "mode":         "PAPER" if self.paper else "LIVE",
            "side":         signal.side,
            "entry_price":  round(entry_price, 4),
            "size_usdc":    self.size_usdc,
            "r2":           pos.r2,
            "slope":        pos.slope,
            "spread":       pos.spread_at_entry,
            "slippage":     pos.slippage,
            "mkt_elapsed":  pos.mkt_elapsed_at_entry,
            "mkt_remaining": pos.mkt_remaining_at_entry,
            "up_mid":       round(self._mid("up"), 4),
            "down_mid":     round(self._mid("down"), 4),
            "btc_price":    round(self.btc.price, 2),
        })

    async def _exit_position(self, pos: Position, exit_type: str, pnl: float) -> None:
        current_price = self._mid(pos.side)
        if current_price <= 0:
            current_price = pos.entry_price

        if not self.paper and self.bot:
            if pos.order_id is None:
                self.log.add(
                    f"EXIT {pos.side.upper()} without entry order_id; attempting live SELL anyway",
                    "warning",
                )
            sell_price = self._mid(pos.side)
            if sell_price <= 0:
                self.log.add(
                    f"SELL skipped for {pos.side.upper()} - invalid current price",
                    "warning",
                )
                return

            if not self.market.current_market:
                self.log.add("SELL skipped - no active market", "warning")
                return

            token_id = self.market.current_market.token_ids.get(pos.side, "")
            if not token_id:
                self.log.add(f"SELL skipped - missing token_id for {pos.side.upper()}", "warning")
                return

            result = await self.bot.place_order(
                token_id=token_id,
                price=round(sell_price, 4),
                size=round(pos.size, 2),
                side="SELL",
            )
            if not result.success:
                self.log.add(f"SELL order FAILED: {result.message}", "error")
                _log({
                    "event":   "SELL_FAILED",
                    "side":    pos.side,
                    "price":   round(sell_price, 4),
                    "size":    round(pos.size, 2),
                    "reason":  result.message,
                })
                return

            current_price = sell_price

        self.positions.close_position(pos.id, pnl)
        self.stats.trades_closed += 1
        self.stats.total_pnl += pnl
        self.stats.record_trade(pnl >= 0, pnl)

        if pnl >= 0:
            self.stats.wins += 1
            level = "success"
        else:
            self.stats.losses += 1
            level = "error"

        self.log.add(
            f"CLOSE {pos.side.upper()} @ {current_price:.4f}  PnL {pnl:+.4f}  ({exit_type})",
            level,
        )

        # Market time remaining at the moment of exit
        mkt = self.market.current_market
        mkt_remaining_exit = -1
        if mkt:
            end_ts = mkt.end_timestamp()
            if end_ts:
                mkt_remaining_exit = max(0, int(end_ts - time.time()))

        _log({
            "event":                "EXIT",
            "side":                 pos.side,
            "entry_price":          round(pos.entry_price, 4),
            "exit_price":           round(current_price, 4),
            "pnl":                  round(pnl, 4),
            "outcome":              "WIN" if pnl >= 0 else "LOSS",
            "exit_type":            exit_type,
            "hold_time":            round(pos.get_hold_time(), 1),
            # entry-context (carried from Position)
            "r2":                   pos.r2,
            "slope":                pos.slope,
            "spread_at_entry":      pos.spread_at_entry,
            "slippage":             pos.slippage,
            "mkt_elapsed_entry":    pos.mkt_elapsed_at_entry,
            "mkt_remaining_entry":  pos.mkt_remaining_at_entry,
            # exit-context
            "mkt_remaining_exit":   mkt_remaining_exit,
            "up_mid":               round(self._mid("up"), 4),
            "down_mid":             round(self._mid("down"), 4),
            "btc_price":            round(self.btc.price, 2),
        })

    def _emergency_close_all(self) -> None:
        """Force-close all positions on market rotation."""
        prices = self._prices()
        for pos in self.positions.get_all_positions():
            price = prices.get(pos.side, pos.entry_price)
            pnl   = pos.get_pnl(price)
            self.positions.close_position(pos.id, pnl)
            self.stats.trades_closed += 1
            self.stats.total_pnl += pnl
            self.stats.record_trade(pnl >= 0, pnl)
            self.log.add(
                f"FORCE-CLOSE {pos.side.upper()} (market rotation) PnL {pnl:+.4f}",
                "warning",
            )
            _log({
                "event":       "FORCE_CLOSE",
                "side":        pos.side,
                "entry_price": round(pos.entry_price, 4),
                "exit_price":  round(price, 4),
                "pnl":         round(pnl, 4),
                "outcome":     "WIN" if pnl >= 0 else "LOSS",
                "hold_time":   round(pos.get_hold_time(), 1),
                "reason":      "market_rotation",
            })

# =============================================================================
#  Entry point
# =============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Automated Polymarket Trend-Following Bot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--coin",       default=COIN,         choices=["BTC"])
    p.add_argument("--size",       type=float, default=SIZE_USDC,     help="USDC per trade")
    p.add_argument("--tp",         type=float, default=TAKE_PROFIT,   help="Take-profit delta")
    p.add_argument("--sl",         type=float, default=STOP_LOSS,     help="Stop-loss delta")
    p.add_argument("--max-pos",    type=int,   default=MAX_POSITIONS, help="Max open positions")
    p.add_argument("--min-spread", type=float, default=MIN_SPREAD,    help="Max allowed spread")
    p.add_argument("--cooldown",   type=float, default=COOLDOWN,      help="Seconds between trades")
    p.add_argument("--min-hold",   type=float, default=MIN_HOLD_TIME, help="Seconds before SL can fire")
    p.add_argument("--force-exit-before", type=int, default=FORCE_EXIT_BEFORE_EXPIRY,
                   help="Force-close open positions this many seconds before market expiry (0 disables)")
    p.add_argument("--paper",      action="store_true",               help="Paper-trade (no real orders)")
    p.add_argument("--refresh",    type=float, default=UI_REFRESH,    help="UI refresh interval (s)")
    return p


async def main_async(args: argparse.Namespace) -> None:
    paper = args.paper

    trading_bot: Optional[TradingBot] = None
    if not paper:
        private_key  = os.environ.get("POLY_PRIVATE_KEY", "")
        safe_address = os.environ.get("POLY_SAFE_ADDRESS", "")
        if not private_key or not safe_address:
            print(f"{Colors.RED}Error:{Colors.RESET} set POLY_PRIVATE_KEY and POLY_SAFE_ADDRESS "
                  f"(or pass --paper for paper-trading).")
            sys.exit(1)
        config = Config.from_env()
        trading_bot = TradingBot(config=config, private_key=private_key)

    strategy = TrendFollowingStrategy(
        lookback_seconds = LOOKBACK_SECONDS,
        min_samples      = MIN_SAMPLES,
        trend_threshold  = TREND_THRESHOLD,
        min_price_change = MIN_PRICE_CHANGE,
    )

    auto = AutoBot(
        coin          = args.coin,
        strategy      = strategy,
        size_usdc     = args.size,
        take_profit   = args.tp,
        stop_loss     = args.sl,
        max_positions = args.max_pos,
        min_spread    = args.min_spread,
        cooldown      = args.cooldown,
        min_hold_time = args.min_hold,
        force_exit_before = args.force_exit_before,
        paper         = paper,
        bot           = trading_bot,
    )

    display = Display(auto, paper, "trend")
    auto._running = True

    async def ui_loop():
        while auto._running:
            display.render()
            await asyncio.sleep(args.refresh)

    bot_task = asyncio.create_task(auto.run())
    ui_task  = asyncio.create_task(ui_loop())

    try:
        await asyncio.gather(bot_task, ui_task)
    except asyncio.CancelledError:
        pass
    finally:
        auto._running = False
        ui_task.cancel()
        try:
            await ui_task
        except asyncio.CancelledError:
            pass
        display.render()
        print(f"\n{Colors.BOLD}Final PnL: {auto.stats.total_pnl:+.4f} USDC{Colors.RESET}")


def main() -> None:
    args = build_arg_parser().parse_args()

    if not args.paper:
        print(f"\n{Colors.BOLD}{Colors.RED}⚠  LIVE MODE  –  real USDC will be spent!{Colors.RESET}")
        print("   Add --paper to paper-trade instead.\n")
        confirm = input("   Type  yes  to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()