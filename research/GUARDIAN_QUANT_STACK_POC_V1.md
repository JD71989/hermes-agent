# Guardian Quant Stack PoC V1

## Objective

Evaluate VectorBT and NautilusTrader against Guardian's current research/replay
architecture without changing the production runtime or installing external
dependencies into the base Python environment.

## Isolation

External packages were exercised only inside `.quant_poc_venv`, a local
research environment. Guardian production code does not import either package.

Installed versions in the PoC environment:
- vectorbt 1.1.0
- nautilus_trader 1.231.0
- py-clob-client-v2 1.1.0 for the Nautilus Polymarket adapter smoke test

## VectorBT comparison

Workload:
- 5,000 synthetic daily price points
- 1,711 valid fast/slow SMA combinations (windows 2..60)
- all-in long-only signal semantics
- next-bar/close timing aligned between engines
- no fees for numerical conformance

Guardian-native result:
- 1,711 combinations in 0.7545 seconds

VectorBT result:
- 1,711 portfolio configurations in 7.6673 seconds

The workload-specific runtime ratio was about 10.16x in favor of the
Guardian-native sweep. This is not a general claim that Guardian is faster than
VectorBT: VectorBT was running a full portfolio simulation over the parameter
matrix while the native harness computes aggregate strategy metrics.

Numerical conformance on the 6/22 strategy:
- total return delta: 5.6e-15
- max drawdown delta: 1.0e-15
- trade/order count: identical at 255 when counting order-side changes
- Sharpe differed because annualization conventions were different; this is
  not treated as a numerical defect.

A 10 bps fee comparison differed slightly because the native benchmark applies
a vectorized cost deduction while VectorBT applies portfolio-level execution
fees. Fee accounting should remain governed by Guardian's dedicated economics
model rather than using this sweep kernel as the final execution model.

## NautilusTrader compatibility

Verified:
- NautilusTrader 1.231.0 imports on Python 3.13.15 / Windows x64.
- BacktestEngine can be instantiated and disposed successfully.
- The optional Polymarket adapter initially failed because `py-clob-client-v2`
  was an undeclared base dependency. Installing the documented optional client
  dependency in the isolated PoC environment made the Polymarket adapter import
  successfully.
- Available Polymarket components include data and execution client factories.

Not yet proven:
- Guardian event-by-event replay equivalence against a real Nautilus backtest.
- Full Pump.fun adapter compatibility.
- Performance of Nautilus against Guardian on the same event stream.

## Decision

Do not replace Guardian's current research engine with VectorBT or NautilusTrader.

Use the results as follows:
- VectorBT: reference implementation and optional external research comparator.
- NautilusTrader: isolated integration candidate, especially for event-driven
  simulation and future venue adapters.
- Guardian native engine: keep as the current canonical research path.

## Next PoC

Build a minimal Nautilus event-replay study using the same Guardian synthetic
event stream and compare ordering, timestamps, fills, portfolio state and
determinism. Only after that comparison should any deeper integration be
considered.

Live execution remains locked.
