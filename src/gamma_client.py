import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from .http import ThreadLocalSessionMixin

class GammaClient(ThreadLocalSessionMixin):

    DEFAULT_HOST = "https://gamma-api.polymarket.com"

    # Supported coins and their slug prefixes
    COIN_SLUGS = {
        "BTC": "btc-updown-5m"
    }

    def __init__(self, host: str = DEFAULT_HOST, timeout: int = 10):

        super().__init__()
        self.host = host.rstrip("/")
        self.timeout = timeout

    def get_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:

        url = f"{self.host}/markets/slug/{slug}"

        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    def get_current_5m_market(self, coin: str) -> Optional[Dict[str, Any]]:

        coin = coin.upper()
        if coin not in self.COIN_SLUGS:
            raise ValueError(f"Unsupported coin: {coin}. Use: {list(self.COIN_SLUGS.keys())}")

        prefix = self.COIN_SLUGS[coin]

        # Calculate current and next 5-minute window timestamps
        now = datetime.now(timezone.utc)

        # Round to current 5-minute window
        minute = (now.minute // 5) * 5
        current_window = now.replace(minute=minute, second=0, microsecond=0)
        current_ts = int(current_window.timestamp())

        # Try current window
        slug = f"{prefix}-{current_ts}"
        market = self.get_market_by_slug(slug)

        if market and market.get("acceptingOrders"):
            return market

        # Try next window (in case current just ended)
        next_ts = current_ts + 300  # 5 minutes
        slug = f"{prefix}-{next_ts}"
        market = self.get_market_by_slug(slug)

        if market and market.get("acceptingOrders"):
            return market

        # Try previous window (might still be active)
        prev_ts = current_ts - 300
        slug = f"{prefix}-{prev_ts}"
        market = self.get_market_by_slug(slug)

        if market and market.get("acceptingOrders"):
            return market

        return None

    def get_next_5m_market(self, coin: str) -> Optional[Dict[str, Any]]:

        coin = coin.upper()
        if coin not in self.COIN_SLUGS:
            raise ValueError(f"Unsupported coin: {coin}")

        prefix = self.COIN_SLUGS[coin]
        now = datetime.now(timezone.utc)

        # Calculate next 5-minute window
        minute = ((now.minute // 5) + 1) * 5
        if minute >= 60:
            next_window = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
        else:
            next_window = now.replace(minute=minute, second=0, microsecond=0)

        next_ts = int(next_window.timestamp())
        slug = f"{prefix}-{next_ts}"

        return self.get_market_by_slug(slug)

    def parse_token_ids(self, market: Dict[str, Any]) -> Dict[str, str]:

        clob_token_ids = market.get("clobTokenIds", "[]")
        token_ids = self._parse_json_field(clob_token_ids)

        outcomes = market.get("outcomes", '["Up", "Down"]')
        outcomes = self._parse_json_field(outcomes)

        return self._map_outcomes(outcomes, token_ids)

    def parse_prices(self, market: Dict[str, Any]) -> Dict[str, float]:

        outcome_prices = market.get("outcomePrices", '["0.5", "0.5"]')
        prices = self._parse_json_field(outcome_prices)

        outcomes = market.get("outcomes", '["Up", "Down"]')
        outcomes = self._parse_json_field(outcomes)

        return self._map_outcomes(outcomes, prices, cast=float)

    @staticmethod
    def _parse_json_field(value: Any) -> List[Any]:
        """Parse a field that may be a JSON string or a list."""
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _map_outcomes(
        outcomes: List[Any],
        values: List[Any],
        cast=lambda v: v
    ) -> Dict[str, Any]:
        """Map outcome labels to values with optional casting."""
        result: Dict[str, Any] = {}
        for i, outcome in enumerate(outcomes):
            if i < len(values):
                result[str(outcome).lower()] = cast(values[i])
        return result

    def get_market_info(self, coin: str) -> Optional[Dict[str, Any]]:

        market = self.get_current_5m_market(coin)
        if not market:
            return None

        token_ids = self.parse_token_ids(market)
        prices = self.parse_prices(market)

        return {
            "slug": market.get("slug"),
            "question": market.get("question"),
            "end_date": market.get("endDate"),
            "token_ids": token_ids,
            "prices": prices,
            "accepting_orders": market.get("acceptingOrders", False),
            "best_bid": market.get("bestBid"),
            "best_ask": market.get("bestAsk"),
            "spread": market.get("spread"),
            "raw": market,
        }
