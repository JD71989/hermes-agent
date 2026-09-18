# Guardian Quant Stack PoC V1

## Objective

Compare the Guardian-native research path with current upstream approaches before
making any external dependency decision.

## External projects checked

VectorBT 1.1.0, NautilusTrader 1.231.0/2.x transition, OpenAlice AutoQuant,
and Microsoft RD-Agent(Q).

## VectorBT isolated test

A dedicated virtual environment was used; the Guardian repository dependency set
was not changed.

VectorBT 1.1.0 imported successfully after pinning Plotly to 6.9.0. The unbounded
upstream Plotly dependency currently resolves Plotly 7.x on this environment, and
that combination failed at import because VectorBT 1.1.0 still registers the
legacy Plotly scattermapbox template property.

The compatibility issue is isolated to the PoC environment and was not patched
into Guardian itself.

The same 5,000-bar synthetic SMA workload was run through both engines.
## Comparable results

Guardian-native: 1,711 valid SMA pairs, 0.9856 seconds.

VectorBT: 1,711 SMA pairs, 34.6502 seconds on the same Nitro5 run.

Single pair (6,22), same synthetic series and nominal 10 bps fee:
Guardian total return 0.6571835, max drawdown -0.2787486, Sharpe 0.2572690.
VectorBT total return 0.6568887, max drawdown -0.2787229, Sharpe 0.3090978.

Returns and drawdown are close, but trade-count/Sharpe semantics differ because
the two implementations model signal changes and performance statistics
differently. This is a semantic-comparison item, not a claim that one engine is
economically superior.

The Guardian result is roughly 35x faster in this specific laptop microbenchmark.
This result is not a universal performance claim and should be repeated across
larger workloads and real datasets.

## NautilusTrader isolated test

NautilusTrader 1.231.0 installed on Windows/Python 3.13 and its v1 engine imported
from the backtest.engine module. BacktestEngine() initialized successfully in
about 1.1 seconds and exposes event-driven data/instrument/venue/strategy/run
components.

Current upstream documentation is for NautilusTrader 2.x and uses a different
Python API. The current stable 1.231.0 package cannot use the 2.x import path for
BacktestEngine. A separate 2.0.0rc3 wheel download was attempted for a clean PoC
but the connection was interrupted before completion.

## Decision

Do not add VectorBT or NautilusTrader as Guardian runtime dependencies yet.
Use VectorBT as a benchmark/reference for vectorized research design.

Run a dedicated Nautilus 2.x PoC later, after the 2.x wheel can be obtained
cleanly, and compare it against Guardian's event/replay semantics rather than
rewriting Guardian around it.

Keep RD-Agent(Q) as a research-loop reference until an isolated experiment shows
incremental value.

Keep OpenAlice as an orchestration/provenance reference; do not vendor its
AGPL-3.0-only code into Guardian.

No live execution was enabled or tested.

## Sources

- VectorBT upstream README and pyproject.toml.
- NautilusTrader upstream installation/quickstart and current repository.
- OpenAlice upstream README and AutoQuant delegation skill.
- Microsoft RD-Agent upstream finance quant documentation.
