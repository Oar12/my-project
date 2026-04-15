# Session-wide performance metrics for any trading bot.

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class BotStats:
    """Accumulates session-wide performance metrics."""
    trades_placed: int  = 0
    trades_closed: int  = 0
    wins:          int  = 0
    losses:        int  = 0
    total_pnl:     float = 0.0
    start_time:    float = field(default_factory=time.time)
    last_trades:   deque = field(default_factory=lambda: deque(maxlen=10))

    def record_trade(self, win: bool, pnl: float) -> None:
        """Prepend a closed trade to the last-10 history (newest first)."""
        self.last_trades.appendleft((win, pnl))

    @property
    def win_rate(self) -> float:
        """Win rate as a percentage (0–100). Returns 0 if no trades closed yet."""
        total = self.wins + self.losses
        return self.wins / total * 100 if total else 0.0

    @property
    def uptime(self) -> str:
        """Human-readable HH:MM:SS elapsed since the bot started."""
        secs = int(time.time() - self.start_time)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
