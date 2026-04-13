"""
analyze_trades.py — Post-session trade analysis
Reads trade_log.jsonl and prints a structured performance report.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

LOG_FILE = "trade_log.jsonl"

# =============================================================================
#  Load
# =============================================================================

records = []
path = Path(LOG_FILE)
if not path.exists():
    print(f"❌  {LOG_FILE} not found.")
    sys.exit(1)

with open(path) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass

if not records:
    print("❌  No records parsed — is the file empty?")
    sys.exit(1)

df_all = pd.DataFrame(records)

# Work only with EXIT rows (FORCE_CLOSE counts as a closed trade too)
exits = df_all[df_all["event"].isin(["EXIT", "FORCE_CLOSE"])].copy()

if exits.empty:
    print("❌  No EXIT records found yet — run the bot first.")
    sys.exit(1)

# Numeric coercion (FORCE_CLOSE rows may be missing some optional fields)
num_cols = [
    "pnl", "hold_time", "entry_price", "exit_price",
    "r2", "slope", "spread_at_entry", "slippage",
    "mkt_elapsed_entry", "mkt_remaining_entry", "mkt_remaining_exit",
    "btc_price",
]
for col in num_cols:
    if col in exits.columns:
        exits[col] = pd.to_numeric(exits[col], errors="coerce")

wins   = exits[exits["outcome"] == "WIN"]
losses = exits[exits["outcome"] == "LOSS"]

# =============================================================================
#  Helpers
# =============================================================================

SEP  = "=" * 60
SEP2 = "-" * 50

def pct(n, d):
    return n / d * 100 if d else 0.0

def safe_mean(series):
    s = series.dropna()
    return s.mean() if len(s) else 0.0


# =============================================================================
#  1. Basic summary
# =============================================================================

total_pnl = exits["pnl"].sum()
win_rate  = pct(len(wins), len(exits))
avg_win   = safe_mean(wins["pnl"])
avg_loss  = safe_mean(losses["pnl"])

print(SEP)
print("📊  TRADE ANALYSIS REPORT")
print(SEP)
print(f"\n📈  Total trades : {len(exits)}")
print(f"✅  Wins         : {len(wins)}   ❌  Losses: {len(losses)}")
print(f"🎯  Win rate     : {win_rate:.1f}%")

# =============================================================================
#  2. PnL
# =============================================================================

gross_profit  = wins["pnl"].sum()
gross_loss    = abs(losses["pnl"].sum())
profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
expectancy    = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * abs(avg_loss))
rr_ratio      = abs(avg_win / avg_loss) if avg_loss else float("inf")

pnl_std  = exits["pnl"].std()
sharpe   = exits["pnl"].mean() / pnl_std if pnl_std > 0 else 0.0

print(f"\n{SEP}")
print("💰  PnL ANALYSIS")
print(SEP)
print(f"Total PnL        : {total_pnl:+.4f}")
print(f"Avg win          : {avg_win:+.4f}   Avg loss: {avg_loss:+.4f}")
print(f"Risk/Reward      : {rr_ratio:.2f}")
print(f"Expectancy/trade : {expectancy:+.4f}")
print(f"Profit factor    : {profit_factor:.2f}")
print(f"Sharpe (naive)   : {sharpe:.3f}")

# =============================================================================
#  3. Hold time
# =============================================================================

avg_hold_all    = safe_mean(exits["hold_time"])
avg_hold_wins   = safe_mean(wins["hold_time"])
avg_hold_losses = safe_mean(losses["hold_time"])

print(f"\n{SEP}")
print("⏱️   HOLD TIME")
print(SEP)
print(f"Avg (all)    : {avg_hold_all:.1f}s")
print(f"Avg (wins)   : {avg_hold_wins:.1f}s")
print(f"Avg (losses) : {avg_hold_losses:.1f}s")

if avg_hold_losses > avg_hold_wins * 1.5 and avg_hold_wins > 0:
    diff = avg_hold_losses - avg_hold_wins
    print(f"  ⚠️  You hold losers {diff:.1f}s longer "
          f"({avg_hold_losses / avg_hold_wins:.1f}× longer than winners)")

buckets = [("0-10s", 0, 10), ("10-30s", 10, 30),
           ("30-60s", 30, 60), ("60-120s", 60, 120), ("120s+", 120, 9999)]
print(f"\n{'Bucket':<10} {'Trades':>7} {'WR%':>8} {'AvgPnL':>10} {'TotalPnL':>12}")
print(SEP2)
for name, lo, hi in buckets:
    b = exits[(exits["hold_time"] >= lo) & (exits["hold_time"] < hi)]
    if b.empty:
        continue
    bw = (b["outcome"] == "WIN").sum()
    print(f"{name:<10} {len(b):>7} {pct(bw, len(b)):>7.1f}% "
          f"{b['pnl'].mean():>10.4f} {b['pnl'].sum():>12.4f}")

# =============================================================================
#  4. Market timing
# =============================================================================

if "mkt_elapsed_entry" in exits.columns:
    timing = exits.dropna(subset=["mkt_elapsed_entry"])
    if not timing.empty:
        print(f"\n{SEP}")
        print("🕐  MARKET TIMING  (when in the 5-min window did you enter?)")
        print(SEP)

        time_buckets = [
            ("0–60s",    0,   60),
            ("60–120s",  60,  120),
            ("120–180s", 120, 180),
            ("180–240s", 180, 240),
            ("240–300s", 240, 300),
        ]
        print(f"{'Window':<12} {'Trades':>7} {'WR%':>8} {'AvgPnL':>10} {'TotalPnL':>12}")
        print(SEP2)
        best_name, best_pnl = None, float("-inf")
        for name, lo, hi in time_buckets:
            b = timing[(timing["mkt_elapsed_entry"] >= lo) &
                       (timing["mkt_elapsed_entry"] <  hi)]
            if b.empty:
                continue
            bw = (b["outcome"] == "WIN").sum()
            total = b["pnl"].sum()
            print(f"{name:<12} {len(b):>7} {pct(bw, len(b)):>7.1f}% "
                  f"{b['pnl'].mean():>10.4f} {total:>12.4f}")
            if total > best_pnl:
                best_pnl, best_name = total, name

        if best_name:
            print(f"\n  ✅  Best window: {best_name}")

# =============================================================================
#  5. Signal quality (R²)
# =============================================================================

if "r2" in exits.columns:
    r2_data = exits.dropna(subset=["r2"])
    r2_data = r2_data[r2_data["r2"] > 0]
    if not r2_data.empty:
        print(f"\n{SEP}")
        print("📐  SIGNAL QUALITY  (does higher R² actually predict wins?)")
        print(SEP)

        r2_buckets = [
            ("0.72–0.80", 0.72, 0.80),
            ("0.80–0.90", 0.80, 0.90),
            ("0.90–1.00", 0.90, 1.01),
        ]
        print(f"{'R² bucket':<14} {'Trades':>7} {'WR%':>8} {'AvgPnL':>10} {'TotalPnL':>12}")
        print(SEP2)
        for name, lo, hi in r2_buckets:
            b = r2_data[(r2_data["r2"] >= lo) & (r2_data["r2"] < hi)]
            if b.empty:
                continue
            bw = (b["outcome"] == "WIN").sum()
            print(f"{name:<14} {len(b):>7} {pct(bw, len(b)):>7.1f}% "
                  f"{b['pnl'].mean():>10.4f} {b['pnl'].sum():>12.4f}")

        corr = r2_data["r2"].corr(r2_data["pnl"])
        print(f"\n  Correlation R² ↔ PnL : {corr:.3f}")
        if not math.isnan(corr) and corr < 0.1:
            print("  ⚠️  Weak correlation — R² may not be a reliable filter at current threshold")

# =============================================================================
#  6. Spread at entry
# =============================================================================

if "spread_at_entry" in exits.columns:
    sp_data = exits.dropna(subset=["spread_at_entry"])
    sp_data = sp_data[sp_data["spread_at_entry"] > 0]
    if not sp_data.empty:
        print(f"\n{SEP}")
        print("📏  SPREAD AT ENTRY")
        print(SEP)

        sp_buckets = [
            ("<0.02",     0,    0.02),
            ("0.02-0.03", 0.02, 0.03),
            ("0.03-0.04", 0.03, 0.04),
            ("≥0.04",     0.04, 9),
        ]
        print(f"{'Spread':<14} {'Trades':>7} {'WR%':>8} {'AvgPnL':>10}")
        print(SEP2)
        for name, lo, hi in sp_buckets:
            b = sp_data[(sp_data["spread_at_entry"] >= lo) &
                        (sp_data["spread_at_entry"] <  hi)]
            if b.empty:
                continue
            bw = (b["outcome"] == "WIN").sum()
            print(f"{name:<14} {len(b):>7} {pct(bw, len(b)):>7.1f}% "
                  f"{b['pnl'].mean():>10.4f}")

        print(f"\n  Avg spread on wins   : {safe_mean(wins.get('spread_at_entry', pd.Series())):.4f}")
        print(f"  Avg spread on losses : {safe_mean(losses.get('spread_at_entry', pd.Series())):.4f}")

# =============================================================================
#  7. Directional (UP vs DOWN)
# =============================================================================

print(f"\n{SEP}")
print("📊  DIRECTIONAL ANALYSIS")
print(SEP)

for side in ["up", "down"]:
    s = exits[exits["side"] == side]
    if s.empty:
        continue
    sw = (s["outcome"] == "WIN").sum()
    print(f"{side.upper():<6}  trades={len(s):>3}  WR={pct(sw, len(s)):>5.1f}%  "
          f"PnL={s['pnl'].sum():>+.4f}")

# =============================================================================
#  8. Consecutive losses
# =============================================================================

max_consec = cur = 0
streaks = []
for outcome in exits["outcome"]:
    if outcome == "LOSS":
        cur += 1
        max_consec = max(max_consec, cur)
    else:
        if cur:
            streaks.append(cur)
        cur = 0
if cur:
    streaks.append(cur)

print(f"\n{SEP}")
print("⚠️   RISK METRICS")
print(SEP)
print(f"Max consecutive losses : {max_consec}")
if streaks:
    print(f"Avg loss streak        : {sum(streaks)/len(streaks):.1f}")

# =============================================================================
#  9. Equity curve + drawdown
# =============================================================================

equity   = exits["pnl"].cumsum()
peak     = equity.cummax()
drawdown = peak - equity
max_dd   = drawdown.max()
recovery = abs(total_pnl) / max_dd if max_dd > 0 else float("inf")

print(f"\n{SEP}")
print("📈  EQUITY CURVE")
print(SEP)
print(f"Final PnL       : {total_pnl:+.4f}")
print(f"Peak equity     : {equity.max():.4f}")
print(f"Max drawdown    : {max_dd:.4f}")
print(f"Recovery factor : {recovery:.2f}")

# =============================================================================
#  10. Recommendations
# =============================================================================

recs = []

if expectancy < 0:
    recs.append("⚠️  Negative expectancy — strategy is losing money long-term")

if profit_factor < 1.5:
    recs.append(f"📉  Low profit factor ({profit_factor:.2f}) — improve entry selection or exit timing")

if rr_ratio < 1.5 and len(exits) >= 10:
    recs.append(f"📊  R:R is {rr_ratio:.2f} — aim for 1.5+ (widen TP or tighten SL)")

if avg_hold_losses > avg_hold_wins * 1.5 and avg_hold_wins > 0:
    recs.append(f"⏱️  Set a time-stop at ~{avg_hold_wins * 1.2:.0f}s "
                f"(losers held {avg_hold_losses / avg_hold_wins:.1f}× longer)")

if max_consec >= 4:
    recs.append(f"🛑  {max_consec} consecutive losses seen — consider a circuit-breaker pause")

if "r2" in exits.columns:
    r2_corr = exits["r2"].corr(exits["pnl"])
    if not math.isnan(r2_corr) and r2_corr < 0.05:
        recs.append("📐  R² shows near-zero correlation with PnL — consider raising trend_threshold")

print(f"\n{SEP}")
print("🎯  RECOMMENDATIONS")
print(SEP)
if recs:
    for i, r in enumerate(recs, 1):
        print(f"{i}. {r}")
else:
    print("✅  No major issues detected.")

print(f"\n{SEP}")
print("✅  ANALYSIS COMPLETE")
print(SEP)