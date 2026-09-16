from research.polymarket_forensics import Trade, bucket_price, fingerprint


def t(ts, condition="c1", outcome="Up", side="BUY", price=0.25, size=10):
    return Trade("0xabc", side, "token", condition, size, price, ts,
                 "Bitcoin Up or Down - 5m", "slug", "event", outcome, 0, str(ts))


def test_bucket_price_edges():
    assert bucket_price(0.0) == "0-20c"
    assert bucket_price(0.20) == "20-40c"
    assert bucket_price(0.40) == "40-60c"
    assert bucket_price(0.60) == "60-80c"
    assert bucket_price(0.80) == "80-100c"


def test_fingerprint_is_deterministic():
    rows = [t(3, price=0.60), t(1, price=0.10), t(2, side="SELL", price=0.30)]
    fp = fingerprint(rows)
    assert fp["trade_count"] == 3
    assert fp["markets"] == 1
    assert fp["buy_pct"] == 66.667
    assert fp["sell_pct"] == 33.333
    assert fp["median_trade_interval_seconds"] == 1.0
    assert fp["total_notional_usdc"] == 10.0


def test_empty_fingerprint():
    assert fingerprint([]) == {"trade_count": 0, "markets": 0, "wallet": None}
