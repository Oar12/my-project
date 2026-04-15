from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lib.console import Colors, clear_and_print, format_countdown

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _vis_len(s: str) -> int:
    """Visible (printable) length of a string, ignoring ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))


def _pad_vis(s: str, width: int) -> str:
    """Pad *s* to *width* visible characters (ANSI-aware)."""
    return s + " " * max(0, width - _vis_len(s))

if TYPE_CHECKING:
    from apps.trend_bot import AutoBot


class Display:
    """Renders the full bot state to the terminal in-place."""

    WIDTH = 110

    def __init__(self, bot: "AutoBot", paper: bool, strategy_name: str):
        self.bot = bot
        self.paper = paper
        self.strategy_name = strategy_name

    def render(self) -> None:
        W = self.WIDTH
        b = self.bot
        mkt = b.market.current_market
        stats = b.stats
        lines: list[str] = []

        # Header
        mode = f"{Colors.YELLOW}PAPER{Colors.RESET}" if self.paper else f"{Colors.RED}LIVE{Colors.RESET}"
        conn = f"{Colors.GREEN}● LIVE{Colors.RESET}" if b.market.is_connected else f"{Colors.YELLOW}○ …{Colors.RESET}"
        cd = "--:--"
        if mkt:
            mins, secs = mkt.get_countdown()
            cd = format_countdown(mins, secs)

        lines.append(f"{Colors.BOLD}{'─' * W}{Colors.RESET}")
        lines.append(
            f"  {Colors.BOLD}AutoBot{Colors.RESET}  │  {b.coin}  │  "
            f"Strategy = {Colors.CYAN}{self.strategy_name}{Colors.RESET}  │  "
            f"Mode = {mode}  │  {conn}  │  ends in {cd}  │  up {stats.uptime}"
        )
        lines.append(f"{Colors.BOLD}{'─' * W}{Colors.RESET}")

        # Market question
        q = mkt.question[:70] if mkt else "Discovering market…"
        lines.append(f"  {Colors.DIM}{q}{Colors.RESET}")
        lines.append("")

        # BTC feed row
        btc = b.btc
        btc_conn = (
            f"{Colors.GREEN}● Binance{Colors.RESET}"
            if btc.is_connected
            else f"{Colors.YELLOW}○ Binance{Colors.RESET}"
        )
        btc_price_str = f"${btc.price:,.2f}" if btc.has_data else "--"
        btc_mom30 = btc.momentum(30)
        btc_vol60 = btc.volatility(60)
        mom_str = f"{btc_mom30 * 100:+.3f}%" if btc_mom30 is not None else "--"
        mom_col = Colors.GREEN if (btc_mom30 or 0) >= 0 else Colors.RED
        vol_str = f"{btc_vol60 * 100:.3f}%" if btc_vol60 > 0 else "--"

        # ── Build orderbook data ───────────────────────────────────────────────
        up_ob = b.market.get_orderbook("up")
        down_ob = b.market.get_orderbook("down")

        def fmt(v: float) -> str:
            return f"{v:.4f}" if v > 0 else "   --  "

        up_mid = up_ob.mid_price if up_ob else 0.0
        down_mid = down_ob.mid_price if down_ob else 0.0
        up_bid = up_ob.best_bid if up_ob else 0.0
        up_ask = up_ob.best_ask if up_ob else 0.0
        down_bid = down_ob.best_bid if down_ob else 0.0
        down_ask = down_ob.best_ask if down_ob else 0.0
        up_sp = b.market.get_spread("up")
        down_sp = b.market.get_spread("down")

        # ── Right panel: Last 10 Trades ────────────────────────────────────────
        SPLIT = 80  # visible column where right panel begins
        sep = f"{Colors.DIM}│{Colors.RESET}"
        right_panel: list[str] = [
            f"{sep} {Colors.BOLD}Last 10 Trades:{Colors.RESET}",
        ]
        for win, pnl in list(b.stats.last_trades):
            sym = "W+" if win else "L-"
            col = Colors.GREEN if win else Colors.RED
            right_panel.append(f"{sep} {col}{sym} PnL {pnl:+.4f}{Colors.RESET}")
        # Fill remaining slots up to 10 trades
        for _ in range(10 - len(b.stats.last_trades)):
            right_panel.append(f"{sep}  {Colors.DIM}---{Colors.RESET}")

        # ── Left rows (parallel with right panel) ──────────────────────────────
        left_rows = [
            (   # Row 0 → right panel row 0 (Last 10 Trades header)
                f"  {btc_conn}  BTC {Colors.BOLD}{btc_price_str}{Colors.RESET}  │  "
                f"30s Mom = {mom_col}{mom_str}{Colors.RESET}  │  "
                f"60s Vol = {vol_str}"
            ),
            "",  # Row 1 → trade[0]
            f"  {'':6}  {'UP':^18}   {'DOWN':^18}",  # Row 2 → trade[1]
            (   # Row 3 → trade[2]
                f"  {'Bid':<6}  {Colors.GREEN}{fmt(up_bid):^18}{Colors.RESET}   "
                f"{Colors.RED}{fmt(down_bid):^18}{Colors.RESET}"
            ),
            (   # Row 4 → trade[3]
                f"  {'Ask':<6}  {Colors.GREEN}{Colors.BOLD}{fmt(up_ask):^18}{Colors.RESET}   "
                f"{Colors.RED}{Colors.BOLD}{fmt(down_ask):^18}{Colors.RESET}"
            ),
            f"  {'Spread':<6}  {up_sp:^18.4f}   {down_sp:^18.4f}",  # Row 5 → trade[4]
            "",  # Row 6 → trade[5]
            "",  # Row 7 → trade[6]
            "",  # Row 8 → trade[7]
            "",  # Row 9 → trade[8]
            "",  # Row 10 → trade[9]
        ]

        for left, right in zip(left_rows, right_panel):
            lines.append(_pad_vis(left, SPLIT) + right)
        lines.append("")

        # Open positions
        lines.append(f"  {Colors.BOLD}Open Positions{Colors.RESET}")
        open_pos = b.positions.get_all_positions()
        if not open_pos:
            lines.append(f"  {Colors.DIM}  (none){Colors.RESET}")
        else:
            for pos in open_pos:
                cur = up_mid if pos.side == "up" else down_mid
                upnl = pos.get_pnl(cur)
                pc = Colors.GREEN if upnl >= 0 else Colors.RED
                sc = Colors.GREEN if pos.side == "up" else Colors.RED
                age = int(pos.get_hold_time())
                lines.append(
                    f"  {sc}{pos.side.upper()}{Colors.RESET}  "
                    f"entry={pos.entry_price:.4f}  now={cur:.4f}  "
                    f"uPnL={pc}{upnl:+.4f}{Colors.RESET}  age={age}s  "
                    f"TP={pos.take_profit_price:.4f}  SL={pos.stop_loss_price:.4f}"
                )
        lines.append("")

        # Session stats
        pnl_color = Colors.GREEN if stats.total_pnl >= 0 else Colors.RED
        lines.append(
            f"  {Colors.BOLD}Stats{Colors.RESET}  "
            f"placed={stats.trades_placed}  closed={stats.trades_closed}  "
            f"W/L={stats.wins}/{stats.losses}  WR={stats.win_rate:.0f}%  "
            f"PnL={pnl_color}{stats.total_pnl:+.4f} USDC{Colors.RESET}"
        )
        lines.append(
            f"  cooldown={b.cooldown:.0f}s  min_hold={b.min_hold_time:.0f}s  "
            f"size=${b.size_usdc:.2f}  max_pos={b.positions.max_positions}  "
            f"TP={b.positions.take_profit * 100:.0f}%  SL={b.positions.stop_loss * 100:.0f}%"
        )
        lines.append("")

        # Log
        lines.append(f"  {Colors.BOLD}Log{Colors.RESET}")
        for line in b.log.get_messages():
            lines.append(f"  {line}")
        lines.append("")
        lines.append(f"  {Colors.DIM}Press Ctrl+C to stop{Colors.RESET}")
        lines.append(f"{Colors.BOLD}{'─' * W}{Colors.RESET}")

        clear_and_print(lines)
