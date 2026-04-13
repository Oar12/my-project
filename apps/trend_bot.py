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
from lib.market_manager import MarketManager
from lib.position_manager import PositionManager, Position
from lib.price_tracker import PriceTracker
from lib.console import Colors, format_countdown, LogBuffer
from lib.bot_stats import BotStats
from lib.btc_feed import BtcFeed
from strategies import Signal, BaseStrategy, TrendFollowingStrategy

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
LOOKBACK_SECONDS  = 30.0    # How far back (s) to look when computing the trend
MIN_SAMPLES       = 4       # Minimum price points required before signalling
TREND_THRESHOLD   = 0.75    # Minimum R² score (0–1); higher = cleaner trend required
MIN_PRICE_CHANGE  = 0.001  # Minimum avg per-sample move to ignore noise

# ── Risk controls ─────────────────────────────────────────────────────────────
TAKE_PROFIT   = 0.10   # Close trade when price rises this much above entry (USDC)
STOP_LOSS     = 0.03    # Close trade when price falls this much below entry (USDC)
MIN_SPREAD    = 0.04    # Skip entry if bid-ask spread is wider than this
COOLDOWN      = 20.0    # Minimum seconds between consecutive entries
MIN_HOLD_TIME = 10.0    # SL cannot fire before this many seconds in a position
MAX_POSITIONS = 1       # Maximum concurrent open positions

# ── Trade sizing ──────────────────────────────────────────────────────────────
SIZE_USDC = 5.0         # USDC to spend per trade

# ── Bot settings ──────────────────────────────────────────────────────────────
COIN           = "BTC"  # Coin market to trade (only BTC supported currently)
UI_REFRESH     = 0.5    # Terminal redraw interval in seconds
LOG_BUFFER_SIZE = 8     # Number of recent log lines shown in the terminal UI

# ── Market expiry guard ───────────────────────────────────────────────────────
NO_ENTRY_BEFORE_EXPIRY = 45  # Don't enter a trade if market expires within this many seconds

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
        paper: bool,
        bot: Optional[TradingBot] = None,
    ):
        self.coin          = coin
        self.strategy      = strategy
        self.size_usdc     = size_usdc
        self.min_spread    = min_spread
        self.cooldown      = cooldown
        self.min_hold_time = min_hold_time
        self.paper         = paper
        self.bot           = bot

        self.market    = MarketManager(coin=coin)
        self.tracker   = PriceTracker(lookback_seconds=60, max_history=500)
        self.positions = PositionManager(
            take_profit=take_profit,
            stop_loss=stop_loss,
            max_positions=max_positions,
        )
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

        # 1. Check exits — but respect the min hold time before SL fires
        for pos, exit_type, pnl in self.positions.check_all_exits(prices):
            if exit_type == "stop_loss" and pos.get_hold_time() < self.min_hold_time:
                continue
            await self._exit_position(pos, exit_type, pnl)

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

        mkt = self.market.current_market
        if mkt and mkt.is_ending_soon(NO_ENTRY_BEFORE_EXPIRY):
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

        if not self.paper and self.bot and self.market.current_market:
            token_id = self.market.current_market.token_ids.get(signal.side, "")
            if token_id:
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

        token_id = (
            self.market.current_market.token_ids.get(signal.side, "")
            if self.market.current_market else ""
        )
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

        mode_tag = "[PAPER]" if self.paper else "[LIVE]"
        self.log.add(
            f"{mode_tag} BUY {signal.side.upper()} @ {entry_price:.4f}  "
            f"${self.size_usdc:.2f}  conf={signal.confidence:.2f}  ({signal.reason})",
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

        if not self.paper and self.bot and pos.order_id:
            pass  # TODO: place SELL order in live mode

        self.positions.close_position(pos.id, pnl)
        self.stats.trades_closed += 1
        self.stats.total_pnl += pnl

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
#  Display
# =============================================================================

class Display:
    """Renders the full bot state to the terminal in-place."""

    WIDTH = 110

    def __init__(self, bot: AutoBot, paper: bool, strategy_name: str):
        self.bot           = bot
        self.paper         = paper
        self.strategy_name = strategy_name

    def render(self) -> None:
        W     = self.WIDTH
        b     = self.bot
        mkt   = b.market.current_market
        stats = b.stats
        lines: list[str] = []

        # ── Header ────────────────────────────────────────────────────────────
        mode = f"{Colors.YELLOW}PAPER{Colors.RESET}" if self.paper else f"{Colors.RED}LIVE{Colors.RESET}"
        conn = f"{Colors.GREEN}● LIVE{Colors.RESET}" if b.market.is_connected else f"{Colors.YELLOW}○ …{Colors.RESET}"
        cd = "--:--"
        if mkt:
            mins, secs = mkt.get_countdown()
            cd = format_countdown(mins, secs)

        lines.append(f"{Colors.BOLD}{'─'*W}{Colors.RESET}")
        lines.append(
            f"  {Colors.BOLD}AutoBot{Colors.RESET}  │  {b.coin}  │  "
            f"Strategy = {Colors.CYAN}{self.strategy_name}{Colors.RESET}  │  "
            f"Mode = {mode}  │  {conn}  │  ends in {cd}  │  up {stats.uptime}"
        )
        lines.append(f"{Colors.BOLD}{'─'*W}{Colors.RESET}")

        # ── Market question ───────────────────────────────────────────────────
        q = mkt.question[:70] if mkt else "Discovering market…"
        lines.append(f"  {Colors.DIM}{q}{Colors.RESET}")
        lines.append("")

        # ── BTC feed row ──────────────────────────────────────────────────────
        btc      = b.btc
        btc_conn = (f"{Colors.GREEN}● Binance{Colors.RESET}"
                    if btc.is_connected else f"{Colors.YELLOW}○ Binance{Colors.RESET}")
        btc_price_str = f"${btc.price:,.2f}" if btc.has_data else "--"
        btc_mom30 = btc.momentum(30)
        btc_vol60 = btc.volatility(60)
        mom_str   = f"{btc_mom30*100:+.3f}%" if btc_mom30 is not None else "--"
        mom_col   = Colors.GREEN if (btc_mom30 or 0) >= 0 else Colors.RED
        vol_str   = f"{btc_vol60*100:.3f}%" if btc_vol60 > 0 else "--"

        lines.append(
            f"  {btc_conn}  BTC {Colors.BOLD}{btc_price_str}{Colors.RESET}  │  "
            f"30s Momentum = {mom_col}{mom_str}{Colors.RESET}  │  "
            f"60s Volatility = {vol_str}"
        )
        lines.append("")

        # ── Orderbook prices ──────────────────────────────────────────────────
        up_ob   = b.market.get_orderbook("up")
        down_ob = b.market.get_orderbook("down")

        def fmt(v: float) -> str:
            return f"{v:.4f}" if v > 0 else "   --  "

        up_mid   = up_ob.mid_price   if up_ob   else 0.0
        down_mid = down_ob.mid_price if down_ob else 0.0
        up_bid   = up_ob.best_bid    if up_ob   else 0.0
        up_ask   = up_ob.best_ask    if up_ob   else 0.0
        down_bid = down_ob.best_bid  if down_ob else 0.0
        down_ask = down_ob.best_ask  if down_ob else 0.0
        up_sp    = b.market.get_spread("up")
        down_sp  = b.market.get_spread("down")

        lines.append(f"  {'':6}  {'UP':^18}   {'DOWN':^18}")
        lines.append(f"  {'Bid':<6}  {Colors.GREEN}{fmt(up_bid):^18}{Colors.RESET}   {Colors.RED}{fmt(down_bid):^18}{Colors.RESET}")
        lines.append(f"  {'Ask':<6}  {Colors.GREEN}{Colors.BOLD}{fmt(up_ask):^18}{Colors.RESET}   {Colors.RED}{Colors.BOLD}{fmt(down_ask):^18}{Colors.RESET}")
        lines.append(f"  {'Spread':<6}  {up_sp:^18.4f}   {down_sp:^18.4f}")
        lines.append("")

        # ── Open positions ────────────────────────────────────────────────────
        lines.append(f"  {Colors.BOLD}Open Positions{Colors.RESET}")
        open_pos = b.positions.get_all_positions()
        if not open_pos:
            lines.append(f"  {Colors.DIM}  (none){Colors.RESET}")
        else:
            for pos in open_pos:
                cur  = up_mid if pos.side == "up" else down_mid
                upnl = pos.get_pnl(cur)
                pc   = Colors.GREEN if upnl >= 0 else Colors.RED
                sc   = Colors.GREEN if pos.side == "up" else Colors.RED
                age  = int(pos.get_hold_time())
                lines.append(
                    f"  {sc}{pos.side.upper()}{Colors.RESET}  "
                    f"entry={pos.entry_price:.4f}  now={cur:.4f}  "
                    f"uPnL={pc}{upnl:+.4f}{Colors.RESET}  age={age}s  "
                    f"TP={pos.take_profit_price:.4f}  SL={pos.stop_loss_price:.4f}"
                )
        lines.append("")

        # ── Session stats ─────────────────────────────────────────────────────
        pnl_color = Colors.GREEN if stats.total_pnl >= 0 else Colors.RED
        lines.append(
            f"  {Colors.BOLD}Stats{Colors.RESET}  "
            f"placed={stats.trades_placed}  closed={stats.trades_closed}  "
            f"W/L={stats.wins}/{stats.losses}  WR={stats.win_rate:.0f}%  "
            f"PnL={pnl_color}{stats.total_pnl:+.4f} USDC{Colors.RESET}"
        )
        lines.append(
            f"  cooldown={b.cooldown:.0f}s  min_hold={b.min_hold_time:.0f}s  "
            f"size=${b.size_usdc:.2f}  spread_max={b.min_spread:.3f}  "
            f"max_pos={b.positions.max_positions}"
        )
        lines.append("")

        # ── Log ───────────────────────────────────────────────────────────────
        lines.append(f"  {Colors.BOLD}Log{Colors.RESET}")
        for line in b.log.get_messages():
            lines.append(f"  {line}")
        lines.append("")
        lines.append(f"  {Colors.DIM}Press Ctrl+C to stop{Colors.RESET}")
        lines.append(f"{Colors.BOLD}{'─'*W}{Colors.RESET}")

        print("\033[H\033[J" + "\n".join(lines), flush=True)

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
        paper         = paper,
        bot           = trading_bot,
    )

    display = Display(auto, paper, "trend")

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