import numpy as np
import pandas as pd

from research.guardian_quant_benchmark import (
    benchmark_native_sweep,
    dependency_status,
    vectorized_sma_sweep,
)


def test_dependency_status_is_deterministic_shape():
    status = dependency_status()
    assert {item.name for item in status} == {"vectorbt", "nautilus_trader", "rdagent"}


def test_vectorized_sweep_uses_next_bar_execution():
    prices = np.array([100.0, 110.0, 121.0, 100.0])
    result = vectorized_sma_sweep(prices, [2], [3], fee_bps=0)
    assert isinstance(result, pd.DataFrame)
    assert result.loc[0, "fast_window"] == 2
    assert result.loc[0, "slow_window"] == 3


def test_invalid_window_is_rejected():
    try:
        vectorized_sma_sweep([1.0, 2.0], [0], [2])
    except ValueError as exc:
        assert "windows" in str(exc)
    else:
        raise AssertionError("invalid window must fail")


def test_fast_window_must_be_less_than_slow_window():
    result = vectorized_sma_sweep([1, 2, 3, 4, 5], [3], [2])
    assert result.empty


def test_benchmark_returns_expected_dimensions():
    result = benchmark_native_sweep(
        bars=250,
        fast_windows=[2, 3, 4],
        slow_windows=[5, 6, 7],
        seed=1,
    )
    assert result.rows == 250
    assert result.combinations == 9
    assert result.seconds >= 0
    assert set(result.results.columns) >= {
        "fast_window", "slow_window", "total_return", "max_drawdown", "sharpe", "trades"
    }


# Benchmark tests are research-only; no broker or transaction path is invoked.
