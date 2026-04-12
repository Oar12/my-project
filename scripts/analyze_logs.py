#!/usr/bin/env python3
"""
Trade Log Analyzer

Usage: python analyze_logs.py [trade_log.txt]

Parses the trade log file and provides summary statistics and insights
to help adjust bot thresholds and strategies.
"""

import sys
import re
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

def parse_log_line(line):
    """Parse a single log line into a dict."""
    # Example line: 2026-04-11 14:16:35,123 - ENTER: [PAPER] DOWN @ 0.3300 size=$5.00 conf=0.10 reason='PM down Δ=+0.0100' up_mid=0.7000 down_mid=0.2900 btc_price=72938.01
    # Or: 2026-04-11 14:16:42,456 - EXIT: DOWN entry=0.3300 exit=0.2950 pnl=-0.5303 outcome=LOSS exit_type=stop_loss hold_time=7.1s up_mid=0.7000 down_mid=0.2900 btc_price=72938.01

    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (.+)', line)
    if not timestamp_match:
        return None

    timestamp_str, content = timestamp_match.groups()
    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')

    if content.startswith('ENTER:'):
        # Parse entry
        entry_match = re.match(
            r"ENTER: \[(\w+)\] (\w+) @ ([\d.]+) size=\$([\d.]+) conf=([\d.]+) reason='([^']+)' up_mid=([\d.]+) down_mid=([\d.]+) btc_price=([\d.]+)",
            content
        )
        if entry_match:
            mode, side, entry_price, size, conf, reason, up_mid, down_mid, btc_price = entry_match.groups()
            return {
                'type': 'enter',
                'timestamp': timestamp,
                'mode': mode,
                'side': side,
                'entry_price': float(entry_price),
                'size': float(size),
                'confidence': float(conf),
                'reason': reason,
                'up_mid': float(up_mid),
                'down_mid': float(down_mid),
                'btc_price': float(btc_price)
            }

    elif content.startswith('EXIT:'):
        # Parse exit
        exit_match = re.match(
            r"EXIT: (\w+) entry=([\d.]+) exit=([\d.]+) pnl=([+-]?[\d.]+) outcome=(\w+) exit_type=(\w+) hold_time=([\d.]+)s up_mid=([\d.]+) down_mid=([\d.]+) btc_price=([\d.]+)",
            content
        )
        if exit_match:
            side, entry_price, exit_price, pnl, outcome, exit_type, hold_time, up_mid, down_mid, btc_price = exit_match.groups()
            return {
                'type': 'exit',
                'timestamp': timestamp,
                'side': side,
                'entry_price': float(entry_price),
                'exit_price': float(exit_price),
                'pnl': float(pnl),
                'outcome': outcome,
                'exit_type': exit_type,
                'hold_time': float(hold_time),
                'up_mid': float(up_mid),
                'down_mid': float(down_mid),
                'btc_price': float(btc_price)
            }

    return None

def analyze_logs(log_file):
    """Analyze the trade log and print insights."""
    entries = []
    exits = []
    trades = []  # Will pair entries and exits

    with open(log_file, 'r') as f:
        for line in f:
            parsed = parse_log_line(line.strip())
            if parsed:
                if parsed['type'] == 'enter':
                    entries.append(parsed)
                elif parsed['type'] == 'exit':
                    exits.append(parsed)

    # Pair entries and exits (simple: assume chronological)
    entry_idx = 0
    for exit_data in exits:
        # Find the matching entry (same side, closest timestamp)
        matching_entry = None
        for i in range(entry_idx, len(entries)):
            if entries[i]['side'] == exit_data['side'] and entries[i]['timestamp'] <= exit_data['timestamp']:
                matching_entry = entries[i]
                entry_idx = i + 1
                break

        if matching_entry:
            trade = {**matching_entry, **exit_data}
            trade['type'] = 'trade'
            trades.append(trade)

    if not trades:
        print("No complete trades found in log.")
        return

    # Analysis
    total_trades = len(trades)
    wins = [t for t in trades if t['outcome'] == 'WIN']
    losses = [t for t in trades if t['outcome'] == 'LOSS']
    win_rate = len(wins) / total_trades * 100 if total_trades else 0
    total_pnl = sum(t['pnl'] for t in trades)
    avg_pnl = total_pnl / total_trades if total_trades else 0

    print("=== TRADE ANALYSIS SUMMARY ===")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {len(wins)} ({win_rate:.1f}%)")
    print(f"Losses: {len(losses)} ({100 - win_rate:.1f}%)")
    print(f"Total PnL: ${total_pnl:.4f}")
    print(f"Average PnL per Trade: ${avg_pnl:.4f}")
    print()

    # Exit type breakdown
    exit_types = Counter(t['exit_type'] for t in trades)
    print("Exit Types:")
    for et, count in exit_types.items():
        pct = count / total_trades * 100
        print(f"  {et}: {count} ({pct:.1f}%)")
    print()

    # Side breakdown
    sides = Counter(t['side'] for t in trades)
    print("Trades by Side:")
    for side, count in sides.items():
        side_trades = [t for t in trades if t['side'] == side]
        side_wins = [t for t in side_trades if t['outcome'] == 'WIN']
        side_win_rate = len(side_wins) / len(side_trades) * 100 if side_trades else 0
        side_avg_pnl = sum(t['pnl'] for t in side_trades) / len(side_trades) if side_trades else 0
        print(f"  {side}: {count} trades, {len(side_wins)} wins ({side_win_rate:.1f}%), avg PnL ${side_avg_pnl:.4f}")
    print()

    # Hold time analysis
    hold_times = [t['hold_time'] for t in trades]
    if hold_times:
        avg_hold = sum(hold_times) / len(hold_times)
        print(f"Average Hold Time: {avg_hold:.1f}s")
        print(f"Min Hold Time: {min(hold_times):.1f}s")
        print(f"Max Hold Time: {max(hold_times):.1f}s")
    print()

    # Confidence analysis
    confs = [t['confidence'] for t in trades]
    if confs:
        avg_conf = sum(confs) / len(confs)
        print(f"Average Confidence: {avg_conf:.2f}")
        # Win rate by confidence bins
        bins = [(0, 0.3), (0.3, 0.6), (0.6, 1.0)]
        print("Win Rate by Confidence:")
        for low, high in bins:
            bin_trades = [t for t in trades if low <= t['confidence'] < high]
            if bin_trades:
                bin_wins = sum(1 for t in bin_trades if t['outcome'] == 'WIN')
                bin_rate = bin_wins / len(bin_trades) * 100
                print(f"  {low:.1f}-{high:.1f}: {bin_wins}/{len(bin_trades)} ({bin_rate:.1f}%)")
    print()

    # Recommendations
    print("=== RECOMMENDATIONS ===")
    if win_rate < 50:
        print("- Win rate below 50%. Consider tightening entry conditions or adjusting TP/SL.")
    if avg_pnl < 0:
        print("- Negative average PnL. Review strategy parameters.")

    if 'stop_loss' in exit_types and exit_types['stop_loss'] > exit_types.get('take_profit', 0):
        print("- More losses from stop-loss than take-profit. Consider widening SL or narrowing TP.")

    if avg_hold < 10:
        print("- Very short hold times. May indicate noisy signals; consider longer cooldown.")

    if sides['UP'] > sides.get('DOWN', 0) * 2 or sides['DOWN'] > sides.get('UP', 0) * 2:
        print("- Imbalanced side distribution. Strategy may be biased; check for market conditions.")

    print("\nRun again after more trades for better insights.")

if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else 'trade_log.txt'
    if not Path(log_file).exists():
        print(f"Log file '{log_file}' not found.")
        sys.exit(1)

    analyze_logs(log_file)