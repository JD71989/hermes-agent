# Guardian Quant Stack Benchmark V1

## Scope

Evaluate external quant projects for architectural fit before adding dependencies.
This benchmark does not install or vendor external frameworks.

## Reviewed projects

- OpenAlice: orchestration/workspace model and AutoQuant research workflow.
- NautilusTrader: event-driven Rust engine, deterministic backtest/simulation, live adapters.
- VectorBT: vectorized research, parameter broadcasting, large-scale sweeps, portfolio analytics.
- RD-Agent(Q): iterative hypothesis, experiment, feedback, factor/model co-optimization.

## Local preflight

- Python: 3.13.15
- NumPy: 2.5.2
- pandas: available
- numba: not installed
- vectorbt: not installed
- nautilus_trader: not installed
- rdagent: not installed
- Rust/Cargo: not on PATH

## Guardian-native benchmark

A vectorized SMA parameter-sweep harness was implemented to validate the research
pattern without pulling in external dependencies. The benchmark uses next-bar
execution semantics and optional fee deductions.

Run: 5,000 synthetic bars, 569 valid fast/slow combinations.
Elapsed time on Nitro5: 0.3165 seconds.

The synthetic run is a performance/implementation check only. Its strategy metrics
are not evidence of a trading edge and must not be used as investment results.

## Decision

Do not integrate any external project yet.

Next PoC targets:

1. Compare Guardian replay semantics against a small NautilusTrader PoC.
2. Benchmark Guardian-native vectorized sweeps against VectorBT in an isolated environment.
3. Evaluate an RD-Agent-style hypothesis/experiment loop without giving the LLM trading authority.
4. Keep OpenAlice as an orchestration/reference architecture rather than a Guardian dependency.

Live trading remains locked.
