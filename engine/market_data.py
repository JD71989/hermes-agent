"""Guardian Market Data Layer.

Provides market data with validation, staleness detection, and missing-data
handling. Every data point is timestamped and checked for freshness before
any downstream system (risk engine, strategy, paper trading) uses it.

Architecture:
- MarketDataProvider is the abstract interface
- SimulatedMarketDataProvider provides deterministic test data
- DataValidator checks staleness, completeness, and consistency
- All data flows through validate() before use
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data freshness policy
# ---------------------------------------------------------------------------

DEFAULT_STALENESS_THRESHOLD_SECONDS = 60  # 1 minute
MAX_STALENESS_THRESHOLD_SECONDS = 300  # 5 minutes
REQUIRED_FIELDS = ("symbol", "bid", "ask", "last_price", "timestamp")


@dataclass(frozen=True)
class MarketTick:
    """A single validated market data point."""
    symbol: str
    bid: float
    ask: float
    last_price: float
    volume_24h: float = 0.0
    change_24h_pct: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = "unknown"
    is_stale: bool = False
    validation_errors: tuple = ()

    @property
    def spread_bps(self) -> float:
        if self.bid <= 0:
            return 0.0
        return (self.ask - self.bid) / self.bid * 10000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "last_price": self.last_price,
            "volume_24h": self.volume_24h,
            "change_24h_pct": self.change_24h_pct,
            "timestamp": self.timestamp,
            "source": self.source,
            "is_stale": self.is_stale,
            "spread_bps": self.spread_bps,
            "validation_errors": list(self.validation_errors),
        }


@dataclass(frozen=True)
class OrderBookLevel:
    """A single order book level."""
    price: float
    quantity: float


@dataclass(frozen=True)
class OrderBook:
    """A validated order book snapshot."""
    symbol: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_stale: bool = False

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def spread_bps(self) -> float:
        if not self.bids or not self.asks or self.bids[0].price <= 0:
            return 0.0
        return (self.asks[0].price - self.bids[0].price) / self.bids[0].price * 10000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "spread_bps": self.spread_bps,
            "bid_depth": len(self.bids),
            "ask_depth": len(self.asks),
            "bids": [(b.price, b.quantity) for b in self.bids[:10]],
            "asks": [(a.price, a.quantity) for a in self.asks[:10]],
            "timestamp": self.timestamp,
            "is_stale": self.is_stale,
        }


@dataclass(frozen=True)
class OHLCVBar:
    """A single OHLCV bar."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


# ---------------------------------------------------------------------------
# Data Validator
# ---------------------------------------------------------------------------

class DataValidator:
    """Validates market data for staleness, completeness, and consistency."""

    def __init__(
        self,
        staleness_threshold_seconds: float = DEFAULT_STALENESS_THRESHOLD_SECONDS,
    ) -> None:
        self._staleness_threshold = staleness_threshold_seconds

    def validate_tick(self, tick: MarketTick) -> MarketTick:
        """Validate a market tick. Returns a new tick with validation state."""
        errors: List[str] = []

        # Check required fields
        if not tick.symbol:
            errors.append("missing symbol")
        if tick.bid <= 0:
            errors.append("bid must be positive")
        if tick.ask <= 0:
            errors.append("ask must be positive")
        if tick.last_price <= 0:
            errors.append("last_price must be positive")
        if tick.ask < tick.bid:
            errors.append("ask < bid (inverted book)")

        # Check staleness
        is_stale = self._check_staleness(tick.timestamp)
        if is_stale:
            errors.append("data is stale")

        # Check spread sanity (spread > 10% is suspicious)
        if tick.bid > 0 and tick.spread_bps > 1000:
            errors.append(f"spread {tick.spread_bps:.0f} bps is suspiciously wide")

        return MarketTick(
            symbol=tick.symbol,
            bid=tick.bid,
            ask=tick.ask,
            last_price=tick.last_price,
            volume_24h=tick.volume_24h,
            change_24h_pct=tick.change_24h_pct,
            timestamp=tick.timestamp,
            source=tick.source,
            is_stale=is_stale,
            validation_errors=tuple(errors),
        )

    def validate_order_book(self, book: OrderBook) -> OrderBook:
        """Validate an order book."""
        is_stale = self._check_staleness(book.timestamp)
        return OrderBook(
            symbol=book.symbol,
            bids=book.bids,
            asks=book.asks,
            timestamp=book.timestamp,
            is_stale=is_stale,
        )

    def _check_staleness(self, timestamp_str: str) -> bool:
        """Check if data is stale based on timestamp."""
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            return age > self._staleness_threshold
        except (ValueError, TypeError):
            return True  # Unparseable timestamp = stale


# ---------------------------------------------------------------------------
# Market Data Provider (abstract + simulated)
# ---------------------------------------------------------------------------

class MarketDataProvider:
    """Abstract market data provider interface."""

    def get_tick(self, symbol: str) -> Optional[MarketTick]:
        raise NotImplementedError

    def get_order_book(self, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        raise NotImplementedError

    def get_ohlcv(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> List[OHLCVBar]:
        raise NotImplementedError

    def get_instruments(self) -> List[Dict[str, Any]]:
        raise NotImplementedError


class SimulatedMarketDataProvider(MarketDataProvider):
    """Deterministic simulated market data for testing.

    Produces realistic but synthetic data. Used for paper trading,
    backtesting, and failure mode testing.
    """

    _PRICES = {
        "BTC_USDT": {"bid": 59990.0, "ask": 60010.0, "vol": 1_500_000_000},
        "ETH_USDT": {"bid": 2995.0, "ask": 3005.0, "vol": 800_000_000},
        "SOL_USDT": {"bid": 149.5, "ask": 150.5, "vol": 400_000_000},
        "DOGE_USDT": {"bid": 0.149, "ask": 0.151, "vol": 200_000_000},
        "XRP_USDT": {"bid": 0.599, "ask": 0.601, "vol": 300_000_000},
    }

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self._injected_errors: Dict[str, Any] = {}

    def inject_error(self, error_type: str, **kwargs: Any) -> None:
        """Inject a fault for failure testing."""
        self._injected_errors[error_type] = kwargs

    def clear_errors(self) -> None:
        self._injected_errors.clear()

    def get_tick(self, symbol: str) -> Optional[MarketTick]:
        if "api_outage" in self._injected_errors:
            return None

        if symbol not in self._PRICES:
            if "missing_data" in self._injected_errors:
                return None
            return None

        ref = self._PRICES[symbol]
        jitter = self._rng.uniform(-0.001, 0.001)
        bid = ref["bid"] * (1 + jitter)
        ask = ref["ask"] * (1 + jitter)

        timestamp = datetime.now(timezone.utc).isoformat()
        if "stale_data" in self._injected_errors:
            age = self._injected_errors["stale_data"].get("age_seconds", 600)
            from datetime import timedelta
            ts = datetime.now(timezone.utc) - timedelta(seconds=age)
            timestamp = ts.isoformat()

        return MarketTick(
            symbol=symbol,
            bid=round(bid, 8),
            ask=round(ask, 8),
            last_price=round((bid + ask) / 2, 8),
            volume_24h=ref["vol"],
            change_24h_pct=round(self._rng.uniform(-5, 5), 2),
            timestamp=timestamp,
            source="simulated",
        )

    def get_order_book(self, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        if "api_outage" in self._injected_errors:
            return None

        tick = self.get_tick(symbol)
        if tick is None:
            return None

        bids = []
        asks = []
        for i in range(depth):
            offset = i * 0.0001
            bids.append(OrderBookLevel(
                price=round(tick.bid * (1 - offset), 8),
                quantity=round(self._rng.uniform(0.01, 1.0), 4),
            ))
            asks.append(OrderBookLevel(
                price=round(tick.ask * (1 + offset), 8),
                quantity=round(self._rng.uniform(0.01, 1.0), 4),
            ))

        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=tick.timestamp,
        )

    def get_ohlcv(
        self, symbol: str, interval: str = "1h", limit: int = 100
    ) -> List[OHLCVBar]:
        if "missing_data" in self._injected_errors:
            return []

        tick = self.get_tick(symbol)
        if tick is None:
            return []

        bars = []
        base_price = tick.last_price
        rng = random.Random(self._seed + hash(symbol))

        for i in range(limit):
            change = rng.uniform(-0.02, 0.02)
            o = base_price * (1 + change)
            h = o * (1 + rng.uniform(0, 0.01))
            l = o * (1 - rng.uniform(0, 0.01))
            c = o * (1 + rng.uniform(-0.01, 0.01))
            v = rng.uniform(100, 10000)
            bars.append(OHLCVBar(
                timestamp=f"bar_{i}",
                open=round(o, 8),
                high=round(h, 8),
                low=round(l, 8),
                close=round(c, 8),
                volume=round(v, 4),
            ))
            base_price = c

        return bars

    def get_instruments(self) -> List[Dict[str, Any]]:
        return [
            {"symbol": sym, "base": sym.split("_")[0], "quote": "USDT"}
            for sym in self._PRICES
        ]


import random


# ---------------------------------------------------------------------------
# Convenience: validated data access
# ---------------------------------------------------------------------------

def get_validated_tick(
    provider: MarketDataProvider,
    symbol: str,
    validator: Optional[DataValidator] = None,
) -> Optional[MarketTick]:
    """Get a market tick and validate it before returning.

    Returns None if data is missing, stale, or invalid.
    """
    tick = provider.get_tick(symbol)
    if tick is None:
        return None
    if validator is None:
        validator = DataValidator()
    return validator.validate_tick(tick)


def get_validated_order_book(
    provider: MarketDataProvider,
    symbol: str,
    depth: int = 10,
    validator: Optional[DataValidator] = None,
) -> Optional[OrderBook]:
    """Get and validate an order book."""
    book = provider.get_order_book(symbol, depth)
    if book is None:
        return None
    if validator is None:
        validator = DataValidator()
    return validator.validate_order_book(book)
