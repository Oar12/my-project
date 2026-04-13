"""
optimizer.py  —  Simple TP/SL grid search against trade_log.txt

Usage:
    python optimizer.py
    python optimizer.py --log trade_log.txt --size 5.0 --top 20
    python optimizer.py --sort sharpe
"""

import re
import itertools
import argparse
import statistics
from dataclasses import dataclass
from typing import List, Dict

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

LOG_FILE  = "trade_log.txt"
SIZE_USDC = 5.0

TP_VALUES = [0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12, 0.15]
SL_VALUES = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]

# ─────────────────────────────────────────────────────────────────────────────
# Parse
# ─────────────────────────────────────────────────────────────────────────────

EXIT_RE = re.compile(
    r"EXIT:\s(?P<side>UP|DOWN)\s"
    r"entry=(?P<entry>\d+\.\d+)\s"
    r"exit=(?P<exit_p>\d+\.\d+)\s"
    r"pnl=(?P<pnl>[-+]?\d+\.\d+)\s"
    r"outcome=(?P<outcome>WIN|LOSS).*?"
    r"(?:hold_time|hold)=(?P<hold>\d+\.\d+)s"
)


@dataclass
class Trade:
    side:        str
    entry:       float
    exit_price:  float
    actual_pnl:  float
    outcome:     str
    hold:        float
    actual_move: float   # exit − entry


def parse_trades(path: str) -> List[Trade]:
    trades = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = EXIT_RE.search(line)
            if not m:
                continue
            entry  = float(m.group("entry"))
            exit_p = float(m.group("exit_p"))
            trades.append(Trade(
                side        = m.group("side"),
                entry       = entry,
                exit_price  = exit_p,
                actual_pnl  = float(m.group("pnl")),
                outcome     = m.group("outcome"),
                hold        = float(m.group("hold")),
                actual_move = exit_p - entry,
            ))
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Simulation
# ─────────────────────────────────────────────────────────────────────────────

def simulate(trades: List[Trade], tp: float, sl: float, size: float) -> Dict:
    """
    WIN  → exit at min(actual_move, tp)   — tighter TP = smaller gain
    LOSS → exit at −min(actual_drop, sl)  — tighter SL = smaller loss
    """
    pnl_list = []
    for t in trades:
        shares = size / t.entry
        if t.outcome == "WIN":
            pnl_list.append(min(t.actual_move, tp) * shares)
        else:
            pnl_list.append(-min(abs(t.actual_move), sl) * shares)

    wins   = sum(1 for p in pnl_list if p >= 0)
    losses = sum(1 for p in pnl_list if p <  0)
    total  = wins + losses

    avg_pnl      = statistics.mean(pnl_list)
    std_pnl      = statistics.stdev(pnl_list) if len(pnl_list) > 1 else 0.0
    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss   = abs(sum(p for p in pnl_list if p < 0))

    return {
        "tp":            tp,
        "sl":            sl,
        "rr_ratio":      tp / sl,
        "total_pnl":     sum(pnl_list),
        "wins":          wins,
        "losses":        losses,
        "win_rate":      wins / total * 100 if total else 0.0,
        "expectancy":    avg_pnl,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "sharpe":        avg_pnl / std_pnl if std_pnl > 0 else 0.0,
    }


def run_grid(trades: List[Trade], size: float) -> List[Dict]:
    return [
        simulate(trades, tp, sl, size)
        for tp, sl in itertools.product(TP_VALUES, SL_VALUES)
        if tp > sl
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────

def _row(r: Dict) -> str:
    wl = f"{r['wins']}/{r['losses']}"
    return (
        f"  {r['tp']:5.2f}"
        f"  {r['sl']:5.2f}"
        f"  {r['rr_ratio']:4.1f}"
        f"  {r['total_pnl']:+9.4f}"
        f"  {wl:>7}"
        f"  {r['win_rate']:6.1f}%"
        f"  {r['expectancy']:+8.4f}"
        f"  {r['profit_factor']:6.2f}"
        f"  {r['sharpe']:7.3f}"
    )

HEADER = (
    "    TP     SL   R:R      PnL      W/L      WR%  Expect      PF   Sharpe"
)


def print_table(results: List[Dict], sort_by: str, top: int) -> None:
    ranked = sorted(results, key=lambda x: x[sort_by], reverse=True)
    sep    = "─" * len(HEADER)

    print(f"\n{sep}")
    print(f"  TOP {top}  —  sorted by  {sort_by}")
    print(sep)
    print(HEADER)
    print(sep)
    for r in ranked[:top]:
        print(_row(r))
    print(sep)

    best = ranked[0]
    print(
        f"\n  ✓  Best:  TP={best['tp']:.2f}  SL={best['sl']:.2f}  "
        f"PnL={best['total_pnl']:+.4f}  WR={best['win_rate']:.1f}%  "
        f"PF={best['profit_factor']:.2f}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Simple TP/SL grid search")
    parser.add_argument("--log",  default=LOG_FILE)
    parser.add_argument("--size", type=float, default=SIZE_USDC)
    parser.add_argument("--top",  type=int,   default=20)
    parser.add_argument("--sort", default="total_pnl",
                        choices=["total_pnl", "sharpe", "profit_factor", "expectancy"])
    args = parser.parse_args()

    trades = parse_trades(args.log)
    if not trades:
        print(f"No trades found in {args.log}")
        return

    print(f"\nParsed {len(trades)} trades  |  "
          f"{len(TP_VALUES)} TP x {len(SL_VALUES)} SL = {len(TP_VALUES)*len(SL_VALUES)} combos")

    results = run_grid(trades, args.size)
    print_table(results, sort_by=args.sort, top=args.top)

    current = simulate(trades, tp=0.07, sl=0.04, size=args.size)
    print(
        f"  Current (TP=0.07  SL=0.04):  "
        f"PnL={current['total_pnl']:+.4f}  "
        f"WR={current['win_rate']:.1f}%  "
        f"PF={current['profit_factor']:.2f}\n"
    )


if __name__ == "__main__":
    main()