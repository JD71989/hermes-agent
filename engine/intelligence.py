"""Guardian Market Intelligence Layer.

Integrates market research, signal analysis, indicator analysis, and regime
analysis into a unified intelligence pipeline.

Architecture:
- IntelligenceEngine composes DataValidator + indicator analysis + regime detection
- All analysis functions are pure — no I/O, no side effects
- Results are structured and auditable
- Works with the existing research/indicators.py library
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from engine.market_data import MarketTick, OHLCVBar, DataValidator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal analysis
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """A trading signal with confidence."""
    name: str
    direction: str  # "buy", "sell", "hold"
    confidence: float  # 0.0 to 1.0
    reason: str
    indicators: Dict[str, float] = field(default_factory=dict)


def compute_rsi_signal(
    closes: Sequence[float], period: int = 14
) -> Signal:
    """RSI-based signal: oversold → buy, overbought → sell."""
    if len(closes) < period + 1:
        return Signal(name="rsi", direction="hold", confidence=0.0, reason="insufficient data")

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

    if rsi < 30:
        direction = "buy"
        confidence = min(1.0, (30 - rsi) / 30)
    elif rsi > 70:
        direction = "sell"
        confidence = min(1.0, (rsi - 70) / 30)
    else:
        direction = "hold"
        confidence = 0.0

    return Signal(
        name="rsi",
        direction=direction,
        confidence=round(confidence, 4),
        reason=f"RSI={rsi:.1f}",
        indicators={"rsi": round(rsi, 2)},
    )


def compute_macd_signal(
    closes: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Signal:
    """MACD crossover signal."""
    if len(closes) < slow + signal_period:
        return Signal(name="macd", direction="hold", confidence=0.0, reason="insufficient data")

    def _ema(data: Sequence[float], span: int) -> List[float]:
        k = 2 / (span + 1)
        ema_val = [data[0]]
        for i in range(1, len(data)):
            ema_val.append(data[i] * k + ema_val[-1] * (1 - k))
        return ema_val

    fast_ema = _ema(closes, fast)
    slow_ema = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = _ema(macd_line, signal_period)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]

    if len(histogram) < 2:
        return Signal(name="macd", direction="hold", confidence=0.0, reason="insufficient data")

    prev_hist = histogram[-2]
    curr_hist = histogram[-1]

    if prev_hist <= 0 and curr_hist > 0:
        direction = "buy"
        confidence = min(1.0, abs(curr_hist) / (abs(curr_hist) + 1e-8))
    elif prev_hist >= 0 and curr_hist < 0:
        direction = "sell"
        confidence = min(1.0, abs(curr_hist) / (abs(curr_hist) + 1e-8))
    else:
        direction = "hold"
        confidence = 0.0

    return Signal(
        name="macd",
        direction=direction,
        confidence=round(confidence, 4),
        reason=f"MACD histogram={curr_hist:.4f}",
        indicators={
            "macd_line": round(macd_line[-1], 4),
            "signal_line": round(signal_line[-1], 4),
            "histogram": round(curr_hist, 4),
        },
    )


def compute_bband_signal(
    closes: Sequence[float], period: int = 20, std_dev: float = 2.0
) -> Signal:
    """Bollinger Band signal: price near lower band → buy, near upper → sell."""
    if len(closes) < period:
        return Signal(name="bbands", direction="hold", confidence=0.0, reason="insufficient data")

    recent = closes[-period:]
    mean = statistics.fmean(recent)
    std = statistics.stdev(recent) if len(recent) > 1 else 0.0
    upper = mean + std_dev * std
    lower = mean - std_dev * std

    price = closes[-1]
    if std == 0:
        return Signal(name="bbands", direction="hold", confidence=0.0, reason="zero volatility")

    if price <= lower:
        direction = "buy"
        confidence = min(1.0, (lower - price) / (std * std_dev + 1e-8))
    elif price >= upper:
        direction = "sell"
        confidence = min(1.0, (price - upper) / (std * std_dev + 1e-8))
    else:
        direction = "hold"
        confidence = 0.0

    return Signal(
        name="bbands",
        direction=direction,
        confidence=round(confidence, 4),
        reason=f"Price={price:.2f}, BB[{lower:.2f}, {mean:.2f}, {upper:.2f}]",
        indicators={
            "bb_upper": round(upper, 4),
            "bb_middle": round(mean, 4),
            "bb_lower": round(lower, 4),
        },
    )


# ---------------------------------------------------------------------------
# Regime analysis (reuses nexus.py logic conceptually, standalone here)
# ---------------------------------------------------------------------------

def detect_regime(
    closes: Sequence[float],
    vol_high_threshold: float = 0.04,
    vol_low_threshold: float = 0.008,
) -> Dict[str, Any]:
    """Classify market regime from close prices.

    Regimes: trending, ranging, volatile, quiet.
    Pure function, deterministic, no I/O.
    """
    if len(closes) < 20:
        return {
            "regime": "unknown",
            "confidence": 0.0,
            "reason": "insufficient data (need >= 20 points)",
        }

    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] != 0:
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

    if len(returns) < 2:
        return {"regime": "unknown", "confidence": 0.0, "reason": "no returns"}

    mean_ret = statistics.fmean(returns)
    stdev = statistics.stdev(returns)
    if stdev == 0:
        stdev = 1e-12

    trend_strength = abs(mean_ret) / stdev

    if stdev >= vol_high_threshold:
        regime = "volatile"
        confidence = min(1.0, 0.5 + stdev / 0.10)
    elif trend_strength >= 0.5:
        regime = "trending"
        confidence = min(1.0, 0.5 + trend_strength / 2.0)
    elif stdev <= vol_low_threshold:
        regime = "quiet"
        confidence = min(1.0, 0.5 + (vol_low_threshold - stdev) / vol_low_threshold)
    else:
        regime = "ranging"
        confidence = 0.6

    return {
        "regime": regime,
        "confidence": round(confidence, 4),
        "volatility": round(stdev, 6),
        "mean_return": round(mean_ret, 8),
        "trend_strength": round(trend_strength, 4),
    }


# ---------------------------------------------------------------------------
# Intelligence Engine — unified pipeline
# ---------------------------------------------------------------------------

class IntelligenceEngine:
    """Unified market intelligence pipeline.

    Composes signal analysis, regime detection, and indicator computation
    into a single analyzable result.
    """

    def __init__(self) -> None:
        self._validator = DataValidator()

    def analyze_signals(self, closes: Sequence[float]) -> List[Signal]:
        """Compute all trading signals from a price series."""
        signals = [
            compute_rsi_signal(closes),
            compute_macd_signal(closes),
            compute_bband_signal(closes),
        ]
        return signals

    def analyze_regime(self, closes: Sequence[float]) -> Dict[str, Any]:
        """Detect market regime."""
        return detect_regime(closes)

    def full_analysis(
        self,
        closes: Sequence[float],
        volumes: Optional[Sequence[float]] = None,
        tick: Optional[MarketTick] = None,
    ) -> Dict[str, Any]:
        """Run complete intelligence analysis.

        Returns a dict with:
        - signals: list of computed signals
        - regime: regime detection result
        - data_quality: validation results for provided tick
        - consensus: aggregated signal direction
        """
        signals = self.analyze_signals(closes)
        regime = self.analyze_regime(closes)

        # Consensus: weighted average of signal directions
        buy_conf = sum(
            s.confidence for s in signals if s.direction == "buy"
        )
        sell_conf = sum(
            s.confidence for s in signals if s.direction == "sell"
        )
        if buy_conf > sell_conf and buy_conf > 0.3:
            consensus = "buy"
            consensus_confidence = buy_conf / max(len(signals), 1)
        elif sell_conf > buy_conf and sell_conf > 0.3:
            consensus = "sell"
            consensus_confidence = sell_conf / max(len(signals), 1)
        else:
            consensus = "hold"
            consensus_confidence = 0.0

        # Data quality
        data_quality = {}
        if tick is not None:
            validated = self._validator.validate_tick(tick)
            data_quality = {
                "is_stale": validated.is_stale,
                "validation_errors": list(validated.validation_errors),
                "spread_bps": validated.spread_bps,
            }

        return {
            "signals": [asdict(s) for s in signals],
            "regime": regime,
            "consensus": consensus,
            "consensus_confidence": round(consensus_confidence, 4),
            "data_quality": data_quality,
        }
