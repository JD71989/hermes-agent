# Pump.fun V2

## Scope
Deterministic Event -> Feature -> Signal research infrastructure. Live execution remains locked.

## Timestamp invariant
A snapshot at timestamp `t` may only use events where `event.timestamp <= t`.

## Features
Token age, buy/sell flow imbalance, transaction velocity, volume acceleration,
liquidity, market-cap progression, holder concentration, creator share,
bonding-curve position, graduation proximity, post-graduation state, and
slippage/fee-adjusted expected return.

## Signals
The signal layer consumes a FeatureSnapshot and emits `BUY_PAPER` or `HOLD`.
It does not submit transactions and must not contain private-key or wallet logic.

## Video hypotheses
Video observations are registered as hypotheses and must be formalized, replayed,
and measured before being considered viable. No observed video rule is treated as
an established trading edge.
