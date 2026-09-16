from research.pumpfun_economics import PaperTrade, fee_breakdown, pumpswap_fee_rates

def test_bonding_curve_total_fee_is_125_percent():
    c = fee_breakdown(PaperTrade('BUY', 10, 100, 'bonding_curve'))
    assert round(c.total_cost_sol, 8) == 0.125

def test_pumpswap_low_cap_is_125_percent():
    c = fee_breakdown(PaperTrade('BUY', 10, 100, 'graduated'))
    assert round(c.total_cost_sol, 8) == 0.125

def test_pumpswap_high_cap_rate_changes():
    creator, protocol, lp = pumpswap_fee_rates(100000)
    assert (creator, protocol, lp) == (.0005, .0005, .002)
