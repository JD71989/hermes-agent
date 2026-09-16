"""Pump.fun fee-aware paper economics; no wallet or order submission."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PaperTrade:
    side: str
    notional_sol: float
    market_cap_sol: float
    phase: str
    slippage_bps: float = 0.0
    network_fee_sol: float = 0.0

@dataclass(frozen=True)
class CostBreakdown:
    protocol_rate: float
    creator_rate: float
    lp_rate: float
    trading_fee_sol: float
    slippage_sol: float
    network_fee_sol: float
    total_cost_sol: float

def pumpswap_fee_rates(market_cap_sol: float) -> tuple[float, float, float]:
    bands = [(420,.003,.0093,.0002),(1470,.0095,.0005,.002),(2460,.009,.0005,.002),(3440,.0085,.0005,.002),(4420,.008,.0005,.002),(9820,.0075,.0005,.002),(14740,.007,.0005,.002),(19650,.0065,.0005,.002),(24560,.006,.0005,.002),(29470,.0055,.0005,.002),(34380,.005,.0005,.002),(39300,.0045,.0005,.002),(44210,.004,.0005,.002),(49120,.0035,.0005,.002),(54030,.003,.0005,.002),(58940,.00275,.0005,.002),(63860,.0025,.0005,.002),(68770,.00225,.0005,.002),(73681,.002,.0005,.002),(78590,.00175,.0005,.002),(83500,.0015,.0005,.002),(88400,.00125,.0005,.002),(93330,.001,.0005,.002),(98240,.00075,.0005,.002),(float("inf"),.0005,.0005,.002)]
    for ceiling, creator, protocol, lp in bands:
        if market_cap_sol < ceiling: return creator, protocol, lp
    raise AssertionError("unreachable")

def fee_breakdown(trade: PaperTrade) -> CostBreakdown:
    if trade.phase == "bonding_curve": creator, protocol, lp = .003, .0095, 0.0
    elif trade.phase == "graduated": creator, protocol, lp = pumpswap_fee_rates(trade.market_cap_sol)
    else: raise ValueError("unknown market phase")
    fee = trade.notional_sol * (creator + protocol + lp)
    slippage = trade.notional_sol * trade.slippage_bps / 10_000
    total = fee + slippage + trade.network_fee_sol
    return CostBreakdown(protocol, creator, lp, fee, slippage, trade.network_fee_sol, total)
