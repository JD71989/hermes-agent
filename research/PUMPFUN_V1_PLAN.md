# Guardian Pump.fun V1

## Scope

Separate market engine coordinated with Guardian shared infrastructure.
V1 is research/read-only. No wallet signing and no live execution path.

## Market model

Pump.fun begins on a deterministic bonding curve. Buys and sells change the
curve price; graduation moves liquidity to PumpSwap. Strategy logic must model
both phases separately.

## Data pipeline

1. Discover new mints and creation events.
2. Capture on-chain trades/events with slot and block time.
3. Build token lifecycle state.
4. Calculate features from events, not screenshots.
5. Replay historical streams deterministically.
6. Generate signals without execution side effects.
7. Apply risk gate before any simulated order.
8. Record simulated fills, slippage and fees.

## Initial feature families

- token age and event velocity
- buy/sell flow imbalance
- trade-size distribution
- bonding-curve price velocity
- liquidity and estimated price impact
- holder concentration and creator concentration
- creator history where reliably observable
- graduation/migration state
- failed/aborted transaction rate

## Video hypotheses

The supplied videos are source material only. Each claimed setup becomes a
formal hypothesis with explicit entry, exit, invalidation and measurement
rules. No video claim is treated as an edge until replay/backtest evidence
supports it after fees, slippage and failed exits.

## Shared Guardian components

Reuse data storage, event timestamps, replay, risk framework, health checks,
metrics and audit logging where interfaces are genuinely market-neutral.
Keep Pump.fun discovery, feature engineering, signal generation and execution
adapters isolated from Polymarket.

## Execution ladder

DISCOVERY -> RECORD -> REPLAY -> BACKTEST -> PAPER -> VALIDATE -> LIVE

The LIVE stage remains locked until explicit later approval and separate
validation gates are satisfied.
