# Trend-following strategy using linear regression slope + R².

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from strategies.base import BaseStrategy, Signal

if TYPE_CHECKING:
    from lib.btc_feed import BtcFeed
    from lib.price_tracker import PriceTracker


class TrendFollowingStrategy(BaseStrategy): 

    def __init__(
        self,
        lookback_seconds: float = 30.0,    # How far back to look for the trend (in seconds).
        min_samples: int = 4,              # Minimum number of data points required to consider a trend valid.
        trend_threshold: float = 0.75,     # Minimum R² score (0–1) to consider the trend strong enough. Higher = cleaner trend required.
        min_price_change: float = 0.001,  # Minimum average per-sample price move to ignore noise (e.g. 0.0009 = 0.09% per sample).
    ):
        self.lookback_seconds  = lookback_seconds
        self.min_samples       = min_samples
        self.trend_threshold   = trend_threshold
        self.min_price_change  = min_price_change

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_recent_history(self, tracker: "PriceTracker", side: str, lookback: float) -> list:
        """Return price history points from the last `lookback` seconds."""
        history = tracker.get_history(side)
        if not history:
            return []
        cutoff = time.time() - lookback
        return [pt for pt in history if pt.timestamp >= cutoff]

    def _is_price_safe(self, price: float) -> bool:
        """
        Avoid entering when outcome is near-decided (price near 0 or 1).
        Historical data: all entries outside 0.25–0.75 were losses.
        """
        return 0.25 <= price <= 0.75

    def _regression_r2(self, history: list) -> tuple[float, float, float]:
        """
        Compute linear regression slope, R², and total price change.

        Returns (slope, r2, total_change):
          slope        — Price change per second (positive = trending up)
          r2           — Goodness of fit (0=noise, 1=perfect line)
          total_change — Last price minus first price in the window
        """
        if len(history) < 2:
            return 0.0, 0.0, 0.0

        x  = [pt.timestamp for pt in history]
        y  = [pt.price     for pt in history]
        x0 = x[0]
        xs = [t - x0 for t in x]  # Normalize timestamps to start from 0

        n      = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(y)  / n

        ss_xx = sum((xi - mean_x) ** 2 for xi in xs)
        ss_yy = sum((yi - mean_y) ** 2 for yi in y)
        ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(xs, y))

        if ss_xx == 0 or ss_yy == 0:
            return 0.0, 0.0, 0.0

        slope     = ss_xy / ss_xx
        intercept = mean_y - slope * mean_x
        y_pred    = [slope * xi + intercept for xi in xs]
        ss_res    = sum((yi - ypi) ** 2 for yi, ypi in zip(y, y_pred))
        r2        = max(0.0, min(1.0, 1.0 - ss_res / ss_yy))

        return slope, r2, y[-1] - y[0]

    # ── Main evaluation ───────────────────────────────────────────────────────

    def evaluate(
        self,
        up_mid: float,
        down_mid: float,
        up_bid: float,
        up_ask: float,
        down_bid: float,
        down_ask: float,
        tracker: "PriceTracker",
        btc: Optional["BtcFeed"] = None,
    ) -> Optional[Signal]:
        """Evaluate recent trend and return a Signal or None."""
        up_history   = self._get_recent_history(tracker, "up",   self.lookback_seconds)
        down_history = self._get_recent_history(tracker, "down", self.lookback_seconds)

        if len(up_history) < self.min_samples and len(down_history) < self.min_samples:
            return None  # Neither side has enough history yet

        candidates: list[Signal] = []

        # ── Check UP side ─────────────────────────────────────────────────────
        if len(up_history) >= self.min_samples and self._is_price_safe(up_mid):
            slope, r2, total_change = self._regression_r2(up_history)
            avg_move = abs(total_change / max(1, len(up_history) - 1))
            if slope > 0 and r2 >= self.trend_threshold and avg_move >= self.min_price_change:
                candidates.append(Signal(
                    side="up",
                    confidence=r2,
                    slope=slope,
                    reason=f"UP trending up  Δ={total_change:+.4f}  R²={r2:.2f}  slope={slope:+.5f}",
                ))

        # ── Check DOWN side ───────────────────────────────────────────────────
        if len(down_history) >= self.min_samples and self._is_price_safe(down_mid):
            slope, r2, total_change = self._regression_r2(down_history)
            avg_move = abs(total_change / max(1, len(down_history) - 1))
            if slope > 0 and r2 >= self.trend_threshold and avg_move >= self.min_price_change:
                candidates.append(Signal(
                    side="down",
                    confidence=r2,
                    slope=slope,
                    reason=f"DOWN trending up  Δ={total_change:+.4f}  R²={r2:.2f}  slope={slope:+.5f}",
                ))

        if not candidates:
            return None

        # Pick the signal with the highest R² (most consistent trend)
        best = max(candidates, key=lambda s: s.confidence)

        # ── BTC confirmation filter ───────────────────────────────────────────
        if btc and btc.has_data:
            btc_mom = btc.momentum(self.lookback_seconds)
            if btc_mom is not None:
                agrees = (btc_mom > 0 and best.side == "up") or \
                         (btc_mom < 0 and best.side == "down")
                if not agrees:
                    return None  # BTC contradicts Polymarket trend — skip
                best.reason += f"  BTC={btc_mom * 100:+.3f}%"

        return best