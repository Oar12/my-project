"""
Trade log analyzer
Reads trade_log.jsonl and prints a structured performance report.

Usage:
    python analyze_trades.py
    python analyze_trades.py --log path/to/trade_log.jsonl
"""

import sys
import argparse
from pathlib import Path

import pandas as pd

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--log", default="trade_log.jsonl", help="Path to JSONL log file")
args = parser.parse_args()

LOG_FILE = Path(args.log)
if not LOG_FILE.exists():
    print(f"❌  {LOG_FILE} not found")
    sys.exit(1)

# ── Load ──────────────────────────────────────────────────────────────────────

df_raw = pd.read_json(LOG_FILE, lines=True)

# Work only with EXIT events — they carry all entry-context fields too
df = df_raw[df_raw["event"] == "EXIT"].copy().reset_index(drop=True)

if df.empty:
    print("❌  No EXIT events found in log file.")
    sys.exit(1)

df["win"] = df["outcome"] == "WIN"

wins   = df[df["win"]]
losses = df[~df["win"]]
total  = len(df)
n_wins = len(wins)
n_loss = len(losses)
wr     = n_wins / total

# ── Helpers ───────────────────────────────────────────────────────────────────

W    = 62
SEP  = "=" * W
SEP2 = "-" * W

def section(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")

def safe_mean(s: pd.Series) -> float:
    return float(s.mean()) if len(s) > 0 else 0.0

def has_data(col: str) -> bool:
    """Column exists, has non-null values, and is not all-zero/negative-one."""
    return (
        col in df.columns
        and df[col].notna().any()
        and df[col].ne(-1).any()
        and df[col].ne(0).any()
    )


# ── 1. Overview ───────────────────────────────────────────────────────────────

section("📊  OVERVIEW")
print(f"Trades    : {total}  (wins={n_wins}  losses={n_loss})")
print(f"Win rate  : {wr*100:.2f}%")
print(f"Total PnL : {df['pnl'].sum():+.4f}")

# Show session summary from START/STOP events if present
sessions = df_raw[df_raw["event"] == "START"]
if not sessions.empty:
    print(f"\nSessions logged: {len(sessions)}")
    if "mode" in sessions.columns:
        modes = sessions["mode"].value_counts().to_dict()
        print(f"Modes: {modes}")


# ── 2. PnL Analysis ───────────────────────────────────────────────────────────

section("💰  PnL ANALYSIS")

avg_win      = safe_mean(wins["pnl"])
avg_loss     = safe_mean(losses["pnl"])
gross_profit = float(wins["pnl"].sum())
gross_loss   = abs(float(losses["pnl"].sum()))
pf           = gross_profit / gross_loss if gross_loss > 0 else float("inf")
rr           = abs(avg_win / avg_loss)   if avg_loss  != 0 else float("inf")
expectancy   = (wr * avg_win) - ((1 - wr) * abs(avg_loss))
std          = float(df["pnl"].std())
sharpe       = float(df["pnl"].mean()) / std if std > 0 else 0.0

print(f"Avg win         : {avg_win:+.4f}")
print(f"Avg loss        : {avg_loss:+.4f}")
print(f"Risk/Reward     : {rr:.2f}")
print(f"Expectancy      : {expectancy:+.4f} per trade")
print(f"Profit factor   : {pf:.2f}")
print(f"Std dev (PnL)   : {std:.4f}")
print(f"Sharpe (simple) : {sharpe:.3f}")


# ── 3. Hold Time ──────────────────────────────────────────────────────────────

section("⏱️   HOLD TIME ANALYSIS")

avg_hold_all  = float(df["hold_time"].mean())
avg_hold_wins = safe_mean(wins["hold_time"])
avg_hold_loss = safe_mean(losses["hold_time"])

print(f"Avg hold (all)    : {avg_hold_all:.1f}s")
print(f"Avg hold (wins)   : {avg_hold_wins:.1f}s")
print(f"Avg hold (losses) : {avg_hold_loss:.1f}s")

if avg_hold_wins > 0 and avg_hold_loss > avg_hold_wins * 1.5:
    pct_longer = (avg_hold_loss / avg_hold_wins - 1) * 100
    print(f"  ⚠️  Losers held {avg_hold_loss - avg_hold_wins:.1f}s longer ({pct_longer:.0f}% longer than winners)")

HOLD_BUCKETS = [("0-10s", 0, 10), ("10-30s", 10, 30), ("30-60s", 30, 60),
                ("60-120s", 60, 120), ("120s+", 120, 9999)]

print(f"\n{'Bucket':<10} {'Trades':>7} {'Win%':>8} {'Avg PnL':>10} {'Total PnL':>12}")
print(SEP2)
for name, lo, hi in HOLD_BUCKETS:
    b = df[(df["hold_time"] >= lo) & (df["hold_time"] < hi)]
    if len(b):
        flag = "✓" if b["pnl"].sum() > 0 else "✗"
        print(f"{name:<10} {len(b):>7} {b['win'].mean()*100:>7.1f}%"
              f" {b['pnl'].mean():>10.4f} {b['pnl'].sum():>12.4f}  {flag}")

corr_hold = float(df["hold_time"].corr(df["pnl"]))
print(f"\nCorrelation (hold time vs PnL): {corr_hold:.3f}")
if corr_hold < -0.3:
    print("  → Longer holds strongly associated with worse outcomes — shorten trades")


# ── 4. Market Timing ──────────────────────────────────────────────────────────

TIMING_BUCKETS = [
    ("0-60s   (early)",  0,   60),
    ("60-120s",          60,  120),
    ("120-180s  (mid)",  120, 180),
    ("180-240s",         180, 240),
    ("240-300s  (late)", 240, 300),
]

if has_data("mkt_elapsed_entry"):
    section("⏰  MARKET TIMING  (where in the 5-min window did you enter?)")

    print(f"{'Window':<22} {'Trades':>7} {'Win%':>8} {'Avg PnL':>10} {'Total PnL':>12}")
    print(SEP2)
    for name, lo, hi in TIMING_BUCKETS:
        b = df[(df["mkt_elapsed_entry"] >= lo) & (df["mkt_elapsed_entry"] < hi)]
        if len(b):
            flag = "✓" if b["pnl"].sum() > 0 else "✗"
            print(f"{name:<22} {len(b):>7} {b['win'].mean()*100:>7.1f}%"
                  f" {b['pnl'].mean():>10.4f} {b['pnl'].sum():>12.4f}  {flag}")

    corr_timing = float(df["mkt_elapsed_entry"].corr(df["pnl"]))
    print(f"\nCorrelation (elapsed vs PnL): {corr_timing:.3f}")
    if corr_timing > 0.2:
        print("  → Later entries in the window tend to perform better")
    elif corr_timing < -0.2:
        print("  → Earlier entries in the window tend to perform better")
    else:
        print("  → Entry timing shows no strong correlation with outcome")

    print(f"\nAvg time remaining at entry : {df['mkt_remaining_entry'].mean():.0f}s")
    if has_data("mkt_remaining_exit"):
        print(f"Avg time remaining at exit  : {df['mkt_remaining_exit'].mean():.0f}s")
else:
    corr_timing = 0.0


# ── 5. Signal Quality (R²) ────────────────────────────────────────────────────

corr_r2    = 0.0
corr_slope = 0.0

if has_data("r2"):
    section("📐  SIGNAL QUALITY  (R² and slope at entry)")

    R2_BUCKETS = [
        ("0.72-0.80", 0.72, 0.80),
        ("0.80-0.88", 0.80, 0.88),
        ("0.88-0.94", 0.88, 0.94),
        ("0.94-1.00", 0.94, 1.01),
    ]

    print(f"{'R² range':<14} {'Trades':>7} {'Win%':>8} {'Avg PnL':>10}")
    print(SEP2)
    for name, lo, hi in R2_BUCKETS:
        b = df[(df["r2"] >= lo) & (df["r2"] < hi)]
        if len(b):
            flag = "✓" if b["pnl"].mean() > 0 else "✗"
            print(f"{name:<14} {len(b):>7} {b['win'].mean()*100:>7.1f}%"
                  f" {b['pnl'].mean():>10.4f}  {flag}")

    corr_r2 = float(df["r2"].corr(df["pnl"]))
    print(f"\nCorrelation (R² vs PnL)    : {corr_r2:.3f}")
    if corr_r2 > 0.2:
        print("  → Higher R² tends to produce better outcomes ✓")
    elif corr_r2 < -0.2:
        print("  ⚠️  Higher R² is NOT predicting better outcomes — revisit trend_threshold")
    else:
        print("  → R² has little predictive power over trade outcome")

    if has_data("slope"):
        corr_slope = float(df["slope"].corr(df["pnl"]))
        print(f"Correlation (slope vs PnL) : {corr_slope:.3f}")


# ── 6. Entry Quality ──────────────────────────────────────────────────────────

if has_data("spread_at_entry") or has_data("slippage"):
    section("🎯  ENTRY QUALITY")

    if has_data("spread_at_entry"):
        print(f"Avg spread at entry : {df['spread_at_entry'].mean():.4f}")
        print(f"Max spread at entry : {df['spread_at_entry'].max():.4f}")
        corr_spread = float(df["spread_at_entry"].corr(df["pnl"]))
        print(f"Correlation (spread vs PnL): {corr_spread:.3f}")
        if corr_spread < -0.2:
            print("  ⚠️  Wider spreads at entry correlate with worse outcomes")

    if has_data("slippage"):
        print(f"\nAvg slippage (ask - mid) : {df['slippage'].mean():.4f}")
        print(f"Max slippage             : {df['slippage'].max():.4f}")


# ── 7. Directional Analysis ───────────────────────────────────────────────────

section("📊  DIRECTIONAL ANALYSIS")

for side in ["up", "down"]:
    s = df[df["side"] == side]
    if len(s):
        flag = "✓" if s["pnl"].sum() > 0 else "⚠️ "
        print(f"{flag} {side.upper():<5}  trades={len(s):3d}  "
              f"win%={s['win'].mean()*100:5.1f}%  "
              f"pnl={s['pnl'].sum():+.4f}  avg={s['pnl'].mean():+.4f}")


# ── 8. Risk Metrics ───────────────────────────────────────────────────────────

section("⚠️   RISK METRICS")

# Max consecutive losses
max_cl = cur = 0
for o in df["outcome"]:
    cur = cur + 1 if o == "LOSS" else 0
    max_cl = max(max_cl, cur)
print(f"Max consecutive losses : {max_cl}")

# Drawdown
cumulative  = df["pnl"].cumsum()
peak        = cumulative.cummax()
drawdowns   = peak - cumulative
max_dd      = float(drawdowns.max())
peak_equity = float(peak.max())
final_pnl   = float(df["pnl"].sum())

print(f"Max drawdown           : {max_dd:.4f}")
if peak_equity > 0:
    print(f"Max drawdown (%peak)   : {max_dd / peak_equity * 100:.1f}%")
if max_dd > 0:
    print(f"Recovery factor        : {abs(final_pnl) / max_dd:.2f}")


# ── 9. Hourly Performance ─────────────────────────────────────────────────────

if "ts" in df.columns:
    section("🕐  PERFORMANCE BY HOUR")

    df["hour"] = pd.to_datetime(df["ts"]).dt.hour
    hourly = (
        df.groupby("hour")
        .agg(trades=("pnl", "count"), win_rate=("win", "mean"), total_pnl=("pnl", "sum"))
    )

    print(f"{'Hour':<6} {'Trades':>7} {'Win%':>8} {'Total PnL':>12}")
    print(SEP2)
    for hour, row in hourly.iterrows():
        flag = "✓" if row["total_pnl"] > 0 else "✗"
        print(f"{hour:02d}:00  {int(row['trades']):>7} {row['win_rate']*100:>7.1f}%"
              f" {row['total_pnl']:>12.4f}  {flag}")

    worst_hour = int(hourly["total_pnl"].idxmin())
    best_hour  = int(hourly["total_pnl"].idxmax())
    print(f"\nBest hour  : {best_hour:02d}:00")
    print(f"Worst hour : {worst_hour:02d}:00")


# ── 10. Equity Curve Summary ──────────────────────────────────────────────────

section("📈  EQUITY CURVE SUMMARY")
print(f"Final PnL    : {final_pnl:+.4f}")
print(f"Peak equity  : {peak_equity:.4f}")
print(f"Max drawdown : {max_dd:.4f}")


# ── 11. Actionable Recommendations ───────────────────────────────────────────

section("🎯  ACTIONABLE RECOMMENDATIONS")

recs: list[str] = []

if expectancy < 0:
    recs.append("⚠️  Negative expectancy — strategy is losing money long-term")

if pf < 1.5:
    recs.append(f"📉  Low profit factor ({pf:.2f}) — improve entry selection or exits")

if rr < 1.5:
    recs.append(f"📊  Poor risk/reward ({rr:.2f}) — consider wider TP or tighter SL")

if avg_hold_wins > 0 and avg_hold_loss > avg_hold_wins * 1.5:
    recs.append(
        f"⏱️  Set time stop at {avg_hold_wins * 1.2:.0f}s — "
        f"you hold losers {avg_hold_loss / avg_hold_wins:.1f}x longer than winners"
    )

if max_cl >= 4:
    recs.append(f"🛑  Hard stop after {max(2, max_cl // 2)} consecutive losses")

if corr_hold < -0.3:
    recs.append("📉  Strong negative correlation (hold vs PnL) — shorten trade duration")

# Worst hold bucket
for name, lo, hi in HOLD_BUCKETS:
    b = df[(df["hold_time"] >= lo) & (df["hold_time"] < hi)]
    if len(b) >= 3 and float(b["pnl"].sum()) < 0:
        recs.append(f"⛔  Worst hold bucket is {name} — avoid lingering in this range")
        break

# Market timing
if has_data("mkt_elapsed_entry"):
    for name, lo, hi in TIMING_BUCKETS:
        b = df[(df["mkt_elapsed_entry"] >= lo) & (df["mkt_elapsed_entry"] < hi)]
        if len(b) >= 3 and float(b["pnl"].sum()) < 0:
            recs.append(
                f"⏰  Avoid entering {lo}-{hi}s into the market window "
                f"(bucket PnL: {b['pnl'].sum():+.4f})"
            )

# R² not predictive
if has_data("r2") and total >= 20 and abs(corr_r2) < 0.1:
    recs.append("📐  R² has no correlation with outcome — consider revising trend_threshold")

# Directional bias
for side in ["up", "down"]:
    s = df[df["side"] == side]
    if len(s) >= 5 and s["win"].mean() < 0.40:
        recs.append(f"📉  {side.upper()} win rate is {s['win'].mean()*100:.0f}% — consider disabling this side")

if not recs:
    print("✅  No major issues detected. Keep following your plan.")
else:
    for i, r in enumerate(recs, 1):
        print(f"{i}. {r}")

print(f"\n{SEP}\n✅  ANALYSIS COMPLETE\n{SEP}")