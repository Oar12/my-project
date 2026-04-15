from __future__ import annotations

from typing import TYPE_CHECKING

from lib.console import Colors, clear_and_print, format_countdown

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

        lines.append(
            f"  {btc_conn}  BTC {Colors.BOLD}{btc_price_str}{Colors.RESET}  │  "
            f"30s Momentum = {mom_col}{mom_str}{Colors.RESET}  │  "
            f"60s Volatility = {vol_str}"
        )
        lines.append("")

        # Orderbook prices
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

        lines.append(f"  {'':6}  {'UP':^18}   {'DOWN':^18}")
        lines.append(
            f"  {'Bid':<6}  {Colors.GREEN}{fmt(up_bid):^18}{Colors.RESET}   "
            f"{Colors.RED}{fmt(down_bid):^18}{Colors.RESET}"
        )
        lines.append(
            f"  {'Ask':<6}  {Colors.GREEN}{Colors.BOLD}{fmt(up_ask):^18}{Colors.RESET}   "
            f"{Colors.RED}{Colors.BOLD}{fmt(down_ask):^18}{Colors.RESET}"
        )
        lines.append(f"  {'Spread':<6}  {up_sp:^18.4f}   {down_sp:^18.4f}")
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
            f"size=${b.size_usdc:.2f}  spread_max={b.min_spread:.3f}  "
            f"max_pos={b.positions.max_positions}"
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
