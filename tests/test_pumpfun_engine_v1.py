from research.pumpfun_engine import RiskLimits, risk_gate


def test_risk_gate_allows_small_liquid_trade():
    decision = risk_gate(
        token_age_seconds=60,
        liquidity_sol=25,
        creator_share_pct=10,
        estimated_slippage_bps=80,
        requested_position_sol=0.1,
    )
    assert decision.allowed is True
    assert decision.reasons == ()


def test_risk_gate_rejects_multiple_constraints():
    decision = risk_gate(
        token_age_seconds=1200,
        liquidity_sol=2,
        creator_share_pct=50,
        estimated_slippage_bps=500,
        requested_position_sol=1,
        limits=RiskLimits(),
    )
    assert decision.allowed is False
    assert set(decision.reasons) == {
        "position_size_limit", "slippage_limit", "token_age_limit",
        "liquidity_floor", "creator_concentration",
    }


def test_custom_limits_change_decision():
    limits = RiskLimits(max_position_sol=1, min_liquidity_sol=1)
    decision = risk_gate(
        token_age_seconds=30,
        liquidity_sol=2,
        creator_share_pct=5,
        estimated_slippage_bps=50,
        requested_position_sol=0.5,
        limits=limits,
    )
    assert decision.allowed is True
