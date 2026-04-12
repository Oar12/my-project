# Abstract base class and Signal dataclass shared by all strategies.
# Any new strategy must inherit BaseStrategy and implement evaluate().

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from lib.btc_feed import BtcFeed
    from lib.price_tracker import PriceTracker

@dataclass
class Signal:
    """A trading signal produced by a strategy."""
    side: str          # Which token to buy: "up" or "down"
    confidence: float  # 0–1 score, used only for logging (not for sizing)
    reason: str        # Human-readable explanation shown in the UI log

class BaseStrategy(ABC):
    """
    Abstract base class all strategies must implement.
    Each strategy receives full market state and returns a Signal or None.
    """

    @abstractmethod
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
        """Return a Signal to enter a trade, or None to skip this tick."""
