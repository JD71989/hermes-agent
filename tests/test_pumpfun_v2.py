from research.pumpfun_engine import MarketPhase, TokenEvent
from research.pumpfun_features import FeatureConfig, FeatureInput, build_feature_snapshot_v2
from research.pumpfun_signals import SignalConfig, generate_signal
from research.video_hypotheses import Hypothesis, HypothesisRegistry, HypothesisStatus


def event(ts, sol, price=1.0, mcap=10.0, *, phase=MarketPhase.BONDING_CURVE):
    return TokenEvent(str(ts), ts, ts, "MINT", "trade", sol, 0, price, 20, mcap, phase, "CREATOR")


def test_features_are_cutoff_safe():
    events = (event(100, 2, mcap=10), event(110, -1, mcap=20), event(120, 100, mcap=9999))
    snap = build_feature_snapshot_v2(FeatureInput(events), now=115)
    assert snap.timestamp == 115
    assert snap.buy_volume_sol == 2
    assert snap.sell_volume_sol == 1
    assert snap.market_cap_sol == 20
    assert snap.token_age_seconds == 15


def test_flow_imbalance_and_velocity():
    events = tuple(event(ts, 1) for ts in (100, 110, 120))
    snap = build_feature_snapshot_v2(FeatureInput(events), now=120)
    assert round(snap.flow_imbalance, 6) == 1.0
    assert round(snap.tx_velocity_per_min, 6) == 3.0


def test_acceleration_uses_prior_window_only():
    events = (event(0, 1), event(70, 4), event(100, 8))
    snap = build_feature_snapshot_v2(FeatureInput(events), now=100, config=FeatureConfig(acceleration_window_seconds=100))
    assert snap.volume_acceleration > 0


def test_v2_external_concentration_inputs():
    snap = build_feature_snapshot_v2(
        FeatureInput((event(10, 1),), holder_concentration_pct=42, creator_share_pct=31), now=10
    )
    assert snap.holder_concentration_pct == 42
    assert snap.creator_share_pct == 31


def test_signal_is_paper_only():
    events = tuple(event(ts, 2, price=1) for ts in (0, 10, 20))
    snap = build_feature_snapshot_v2(FeatureInput(events), now=20, config=FeatureConfig(expected_exit_price_sol=2))
    signal = generate_signal(snap, config=SignalConfig())
    assert signal.action == "BUY_PAPER"
    assert signal.mint == "MINT"


def test_graduated_flag_and_proximity():
    snap = build_feature_snapshot_v2(
        FeatureInput((event(50, 1, mcap=80, phase=MarketPhase.GRADUATED),)), now=50
    )
    assert snap.post_graduation is True
    assert snap.graduation_proximity_pct == 0.0


def test_hypothesis_registry_tracks_status_and_metrics():
    registry = HypothesisRegistry()
    registry.add(Hypothesis("VID-001", "flow rises", "imbalance > .2", "BUY", "SELL", "risk gate"))
    assert registry.items["VID-001"].status == HypothesisStatus.OBSERVED
    registry.update_result("VID-001", trades=10, expectancy=0.03)
    assert registry.items["VID-001"].status == HypothesisStatus.TESTED
    assert registry.items["VID-001"].result["trades"] == 10
