from research.pumpfun_paper import PaperLedger


def test_buy_records_costed_position():
    ledger = PaperLedger()
    fill = ledger.execute(mint="M", timestamp=10, side="BUY", quantity_tokens=10,
                          price_sol=1, phase="bonding_curve", market_cap_sol=100)
    assert fill.notional_sol == 10
    assert fill.total_cost_sol > 0
    pos = ledger.position("M")
    assert pos is not None
    assert pos.quantity_tokens == 10
    assert pos.entry_timestamp == 10


def test_round_trip_realizes_net_pnl_after_costs():
    ledger = PaperLedger()
    ledger.execute(mint="M", timestamp=10, side="BUY", quantity_tokens=10,
                   price_sol=1, phase="bonding_curve", market_cap_sol=100)
    ledger.execute(mint="M", timestamp=20, side="SELL", quantity_tokens=10,
                   price_sol=2, phase="bonding_curve", market_cap_sol=100)
    trade = ledger.realized[0]
    assert ledger.position("M") is None
    assert trade.entry_timestamp == 10
    assert trade.exit_timestamp == 20
    assert trade.net_pnl_sol > 0
    assert trade.net_pnl_sol < 10


def test_partial_sell_retains_position():
    ledger = PaperLedger()
    ledger.execute(mint="M", timestamp=10, side="BUY", quantity_tokens=10,
                   price_sol=1, phase="bonding_curve", market_cap_sol=100)
    ledger.execute(mint="M", timestamp=20, side="SELL", quantity_tokens=4,
                   price_sol=2, phase="bonding_curve", market_cap_sol=100)
    pos = ledger.position("M")
    assert pos is not None
    assert pos.quantity_tokens == 6
    assert pos.entry_timestamp == 10
    assert len(ledger.realized) == 1


def test_cannot_oversell():
    ledger = PaperLedger()
    try:
        ledger.execute(mint="M", timestamp=1, side="SELL", quantity_tokens=1,
                       price_sol=1, phase="bonding_curve", market_cap_sol=100)
    except ValueError as exc:
        assert "insufficient" in str(exc)
    else:
        raise AssertionError("oversell must fail")



def test_rejects_invalid_quantity_or_price():
    ledger = PaperLedger()
    for qty, price in ((0, 1), (1, 0), (-1, 1), (1, -1)):
        try:
            ledger.execute(mint="M", timestamp=1, side="BUY", quantity_tokens=qty,
                           price_sol=price, phase="bonding_curve", market_cap_sol=100)
        except ValueError:
            continue
        raise AssertionError("invalid fill inputs must fail")


# This suite never invokes a live transaction path.






