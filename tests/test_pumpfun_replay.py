from research.pumpfun_engine import TokenEvent
from research.pumpfun_features import FeatureConfig
from research.pumpfun_replay import replay_events
from research.pumpfun_signals import SignalConfig


def ev(ts, sol, mint="M1"):
    return TokenEvent(str(ts), ts, ts, mint, "trade", sol, 0, 1.0, 20.0, 10.0)


def test_replay_is_chronological_and_counts_current_event():
    result = replay_events((ev(30, 1), ev(10, 2), ev(20, -1)))
    assert [s.timestamp for s in result.steps] == [10, 20, 30]
    assert result.steps[0].feature_snapshot.buy_volume_sol == 2
    assert result.steps[1].feature_snapshot.sell_volume_sol == 1
    assert result.steps[2].feature_snapshot.buy_volume_sol == 3


def test_replay_does_not_look_ahead():
    result = replay_events((ev(10, 1), ev(20, 100)))
    first = result.steps[0].feature_snapshot
    assert first.buy_volume_sol == 1
    assert first.timestamp == 10


def test_replay_isolates_mints():
    result = replay_events((ev(10, 1, "A"), ev(20, 5, "B"), ev(30, 2, "A")))
    a_steps = [s for s in result.steps if s.mint == "A"]
    assert a_steps[-1].feature_snapshot.buy_volume_sol == 3


def test_empty_replay_is_safe():
    assert replay_events((), feature_config=FeatureConfig(), signal_config=SignalConfig()).steps == ()
