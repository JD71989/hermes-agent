"""Guardian-native quant-stack benchmark and vectorized research baseline.
External frameworks are measured only when installed; no dependency is auto-installed.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import time
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    installed: bool


@dataclass(frozen=True)
class BenchmarkResult:
    rows: int
    combinations: int
    seconds: float
    results: pd.DataFrame


def dependency_status() -> tuple[DependencyStatus, ...]:
    return tuple(
        DependencyStatus(name, importlib.util.find_spec(name) is not None)
        for name in ("vectorbt", "nautilus_trader", "rdagent")
    )


def _sma_matrix(prices: np.ndarray, windows: Sequence[int]) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    if prices.ndim != 1 or len(prices) < 2:
        raise ValueError("prices must be a 1-D array with at least two values")
    out = np.empty((len(windows), len(prices)), dtype=float)
    for i, window in enumerate(windows):
        if window <= 0 or window > len(prices):
            raise ValueError("windows must be positive and fit the price series")
        csum = np.cumsum(np.r_[0.0, prices])
        ma = (csum[window:] - csum[:-window]) / window
        out[i, : window - 1] = np.nan
        out[i, window - 1 :] = ma
    return out


def vectorized_sma_sweep(
    prices: Sequence[float],
    fast_windows: Sequence[int],
    slow_windows: Sequence[int],
    fee_bps: float = 0.0,
) -> pd.DataFrame:
    """Evaluate every fast/slow combination with next-bar execution semantics."""
    if fee_bps < 0:
        raise ValueError("fee_bps must be non-negative")
    prices_np = np.asarray(prices, dtype=float)
    fast = tuple(int(x) for x in fast_windows)
    slow = tuple(int(x) for x in slow_windows)
    fast_ma = _sma_matrix(prices_np, fast)
    slow_ma = _sma_matrix(prices_np, slow)
    returns = np.zeros(len(prices_np), dtype=float)
    returns[1:] = prices_np[1:] / prices_np[:-1] - 1.0
    signal = fast_ma[:, None, :] > slow_ma[None, :, :]
    signal = np.where(np.isnan(fast_ma[:, None, :]) | np.isnan(slow_ma[None, :, :]),
                      False, signal)
    position = np.zeros_like(signal, dtype=float)
    position[:, :, 1:] = signal[:, :, :-1]
    turnover = np.abs(np.diff(position, axis=2, prepend=0.0))
    net_returns = position * returns
    if fee_bps:
        net_returns -= turnover * (fee_bps / 10_000.0)
    total = np.prod(1.0 + net_returns, axis=2) - 1.0
    equity = np.cumprod(1.0 + net_returns, axis=2)
    peaks = np.maximum.accumulate(equity, axis=2)
    drawdown = equity / peaks - 1.0
    max_dd = drawdown.min(axis=2)
    mean = net_returns.mean(axis=2)
    std = net_returns.std(axis=2)
    sharpe = np.divide(mean, std, out=np.zeros_like(mean), where=std > 0) * np.sqrt(252)
    records: list[dict[str, float | int]] = []
    for i, f in enumerate(fast):
        for j, s in enumerate(slow):
            if f >= s:
                continue
            records.append({
                "fast_window": f,
                "slow_window": s,
                "total_return": float(total[i, j]),
                "max_drawdown": float(max_dd[i, j]),
                "sharpe": float(sharpe[i, j]),
                "trades": int(np.count_nonzero(turnover[i, j] > 0)),
            })
    return pd.DataFrame.from_records(records)
def benchmark_native_sweep(
    *,
    bars: int = 5000,
    fast_windows: Sequence[int] = tuple(range(2, 27)),
    slow_windows: Sequence[int] = tuple(range(10, 61, 2)),
    seed: int = 7,
) -> BenchmarkResult:
    if bars < 100:
        raise ValueError("bars must be at least 100")
    rng = np.random.default_rng(seed)
    prices = 100.0 * np.exp(np.cumsum(rng.normal(0.00015, 0.012, bars)))
    start = time.perf_counter()
    results = vectorized_sma_sweep(prices, fast_windows, slow_windows, fee_bps=10.0)
    elapsed = time.perf_counter() - start
    return BenchmarkResult(
        rows=bars,
        combinations=len(results),
        seconds=elapsed,
        results=results,
    )
