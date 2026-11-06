# Pump.fun Paper Execution V1

Paper-only execution and average-cost position accounting.

## Scope
Signals can be translated into simulated fills with explicit protocol fees, slippage, and network costs. No wallet, signer, private key, or transaction submission is present.

## Accounting
BUY adds notional plus execution costs to invested basis. Additional buys preserve the original entry timestamp and recompute average cost. SELL requires sufficient paper inventory and records realised gross and net P&L. Partial sells retain the remaining position.

## Validation
Tests cover fee-aware round trips, partial exits, insufficient inventory, invalid inputs, and entry/exit timestamps.

## Next
Integrate replay signals into this ledger, then add portfolio equity, drawdown, attribution, and replay-to-paper reporting.

Live execution remains locked by design.

Current implementation: deterministic paper fills and realised P&L ledger.

