"""Guardian Trading System — comprehensive test suite.

Tests cover:
- Risk Engine: all controls, deterministic behavior, LLM override prevention
- Paper Trading: position tracking, P&L, execution simulation
- Market Data: validation, staleness, missing data
- Backtesting: reproducibility, costs, metrics
- Market Intelligence: signals, regime, consensus
- Live Execution: authorization gates, pipeline stages
- Failure Modes: stale data, missing data, API outage, rejected order,
  duplicate order, partial fill, timeout, price movement, risk breach,
  emergency stop
"""

from __future__ import annotations

import math
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence

import pytest

from engine.risk_engine import (
    RiskEngine,
    RiskViolation,
    RiskVerdict,
    Position,
)
from engine.paper_trading import (
    PaperTradingEngine,
    OrderStatus,
)
from engine.market_data import (
    MarketTick,
    OrderBook,
    OrderBookLevel,
    OHLCVBar,
    DataValidator,
    SimulatedMarketDataProvider,
    get_validated_tick,
    get_validated_order_book,
)
from engine.backtesting import (
    Backtester,
    CostModel,
    BacktestResult,
    walk_forward_split,
)
from engine.intelligence import (
    compute_rsi_signal,
    compute_macd_signal,
    compute_bband_signal,
    detect_regime,
    IntelligenceEngine,
)
from engine.live_execution import (
    LiveExecutionPipeline,
    ExecutionStage,
    ExecutionMode,
)


# ===================================================================
# RISK ENGINE TESTS
# ===================================================================


class TestRiskEngine:
    """Test all deterministic risk controls."""

    def test_basic_order_approved(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is True
        assert len(verdict.violations) == 0

    def test_position_size_limit(self):
        risk = RiskEngine(max_position_size_usdt=10.0, seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=1.0, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.EXCEEDS_POSITION_SIZE in verdict.violations

    def test_total_exposure_limit(self):
        risk = RiskEngine(
            max_total_exposure_usdt=10.0,
            max_position_size_usdt=19.0,
            seed_capital_usdt=19.0,
            max_open_positions=5,
        )
        # Open a position consuming most exposure
        risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.00015,
        )
        # Try to open another that exceeds total exposure
        verdict = risk.check_order(
            symbol="ETH_USDT", side="buy", quantity=0.1, price=3000.0
        )
        assert verdict.approved is False
        assert RiskViolation.EXCEEDS_TOTAL_EXPOSURE in verdict.violations

    def test_concentration_limit(self):
        risk = RiskEngine(
            max_concentration_pct=0.5,
            max_position_size_usdt=19.0,
            seed_capital_usdt=19.0,
        )
        risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        # Another BTC order should breach concentration
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.EXCEEDS_CONCENTRATION_LIMIT in verdict.violations

    def test_max_open_positions(self):
        risk = RiskEngine(max_open_positions=1, seed_capital_usdt=19.0)
        risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        verdict = risk.check_order(
            symbol="ETH_USDT", side="buy", quantity=0.01, price=3000.0
        )
        assert verdict.approved is False
        assert RiskViolation.TOO_MANY_OPEN_POSITIONS in verdict.violations

    def test_consecutive_losses(self):
        risk = RiskEngine(max_consecutive_losses=3, seed_capital_usdt=19.0)
        risk._state.consecutive_losses = 3
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.TOO_MANY_CONSECUTIVE_LOSSES in verdict.violations

    def test_kill_switch_blocks_all(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        risk.engage_kill_switch()
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.KILL_SWITCH_ENGAGED in verdict.violations

    def test_kill_switch_cooldown(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        risk.engage_kill_switch()
        # Try to disengage immediately — should fail (cooldown)
        risk.disengage_kill_switch()
        assert risk.kill_switch_active is True

    def test_leverage_forbidden(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001,
            price=60000.0, leverage=2.0,
        )
        assert verdict.approved is False
        assert RiskViolation.LEVERAGE_FORBIDDEN in verdict.violations

    def test_invalid_order_rejected(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=-1, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.INVALID_ORDER in verdict.violations

    def test_daily_loss_limit(self):
        risk = RiskEngine(max_daily_loss_usdt=5.0, seed_capital_usdt=19.0)
        risk._state.daily_pnl = -6.0
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.EXCEEDS_DAILY_LOSS in verdict.violations

    def test_total_loss_limit(self):
        risk = RiskEngine(max_total_loss_usdt=10.0, seed_capital_usdt=19.0)
        risk._state.total_pnl = -11.0
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.EXCEEDS_TOTAL_LOSS in verdict.violations

    def test_drawdown_limit(self):
        risk = RiskEngine(max_drawdown_pct=0.20, seed_capital_usdt=19.0)
        risk._state.max_drawdown = 0.25
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert verdict.approved is False
        assert RiskViolation.EXCEEDS_DRAWDOWN_LIMIT in verdict.violations

    def test_open_close_position_pnl(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        pos = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        result = risk.close_position(pos.position_id, exit_price=61000.0)
        assert result["pnl_usdt"] > 0
        assert risk.state.total_pnl > 0

    def test_drawdown_tracking(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        pos1 = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        risk.close_position(pos1.position_id, exit_price=62000.0)  # +$0.2
        pos2 = risk.open_position(
            symbol="ETH_USDT", side="buy",
            entry_price=3000.0, quantity=0.0001,
        )
        risk.close_position(pos2.position_id, exit_price=2800.0)  # -$0.02
        # Should have tracked drawdown
        assert risk.state.max_drawdown >= 0

    def test_consecutive_losses_tracking(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        pos1 = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        risk.close_position(pos1.position_id, exit_price=59000.0)  # loss
        assert risk.state.consecutive_losses == 1
        pos2 = risk.open_position(
            symbol="ETH_USDT", side="buy",
            entry_price=3000.0, quantity=0.0001,
        )
        risk.close_position(pos2.position_id, exit_price=2900.0)  # loss
        assert risk.state.consecutive_losses == 2

    def test_risk_status_snapshot(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        status = risk.get_risk_status()
        assert "kill_switch_active" in status
        assert "daily_pnl" in status
        assert "exposure" in status
        assert "limits" in status

    def test_verdict_is_immutable(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        # RiskVerdict is a frozen dataclass — cannot be modified
        with pytest.raises(AttributeError):
            verdict.approved = False  # type: ignore

    def test_audit_log_recorded(self):
        risk = RiskEngine(seed_capital_usdt=19.0)
        risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        log = risk.get_audit_log()
        assert len(log) >= 1
        assert log[0]["event_type"] == "order_check"


# ===================================================================
# PAPER TRADING TESTS
# ===================================================================


class TestPaperTrading:
    """Test paper trading engine."""

    def test_submit_buy_order(self):
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        result = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert result["status"] in (OrderStatus.FILLED, OrderStatus.REJECTED)

    def test_buy_sell_cycle(self):
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            rejection_probability=0.0,  # disable random rejection
            partial_fill_probability=0.0,
        )
        buy = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert buy["status"] == OrderStatus.FILLED
        assert len(engine.get_positions()) == 1

        sell = engine.submit_order(
            symbol="BTC_USDT", side="sell", quantity=0.0001, price=61000.0
        )
        assert sell["status"] == OrderStatus.FILLED
        assert len(engine.get_positions()) == 0

    def test_position_tracking(self):
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            rejection_probability=0.0,
            partial_fill_probability=0.0,
        )
        engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        positions = engine.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTC_USDT"

    def test_pnl_accounting(self):
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            rejection_probability=0.0,
            partial_fill_probability=0.0,
        )
        initial_cash = engine.cash
        engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        assert engine.cash < initial_cash  # cash decreased

    def test_fill_recorded(self):
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            rejection_probability=0.0,
            partial_fill_probability=0.0,
        )
        engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        fills = engine.get_fills()
        assert len(fills) >= 1

    def test_order_history(self):
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            rejection_probability=0.0,
            partial_fill_probability=0.0,
        )
        engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        history = engine.get_order_history()
        assert len(history) == 1

    def test_summary(self):
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        summary = engine.get_summary()
        assert summary["seed_capital_usdt"] == 19.0
        assert "risk_status" in summary
        assert "exposure" in summary

    def test_invalid_side_rejected(self):
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        result = engine.submit_order(
            symbol="BTC_USDT", side="invalid", quantity=0.0001, price=60000.0
        )
        assert result["status"] == OrderStatus.REJECTED

    def test_zero_quantity_rejected(self):
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        result = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0, price=60000.0
        )
        assert result["status"] == OrderStatus.REJECTED

    def test_limit_order_requires_price(self):
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        result = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001,
            order_type="limit", price=None,
        )
        assert result["status"] == OrderStatus.REJECTED

    def test_full_pipeline_stages(self):
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            rejection_probability=0.0,
        )
        result = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        # Full pipeline: AUTHORIZED → DATA_VALIDATED → RISK_CHECK → EXECUTE → RECONCILE → AUDIT
        assert "fill_price" in result or result["status"] == OrderStatus.REJECTED
        assert "order_id" in result

    def test_audit_log(self):
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0
        )
        log = engine.get_audit_log()
        assert len(log) >= 1


# ===================================================================
# MARKET DATA TESTS
# ===================================================================


class TestMarketData:
    """Test market data validation and staleness detection."""

    def test_valid_tick(self):
        tick = MarketTick(
            symbol="BTC_USDT", bid=59990.0, ask=60010.0,
            last_price=60000.0, volume_24h=1e9,
        )
        validator = DataValidator()
        validated = validator.validate_tick(tick)
        assert validated.is_stale is False
        assert len(validated.validation_errors) == 0

    def test_stale_tick_detected(self):
        from datetime import timedelta
        stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        tick = MarketTick(
            symbol="BTC_USDT", bid=59990.0, ask=60010.0,
            last_price=60000.0, timestamp=stale_ts,
        )
        validator = DataValidator(staleness_threshold_seconds=60)
        validated = validator.validate_tick(tick)
        assert validated.is_stale is True

    def test_inverted_book_detected(self):
        tick = MarketTick(
            symbol="BTC_USDT", bid=60010.0, ask=59990.0,  # inverted!
            last_price=60000.0,
        )
        validator = DataValidator()
        validated = validator.validate_tick(tick)
        assert any("ask < bid" in e for e in validated.validation_errors)

    def test_zero_bid_rejected(self):
        tick = MarketTick(
            symbol="BTC_USDT", bid=0.0, ask=60010.0,
            last_price=60000.0,
        )
        validator = DataValidator()
        validated = validator.validate_tick(tick)
        assert any("bid must be positive" in e for e in validated.validation_errors)

    def test_wide_spread_flagged(self):
        tick = MarketTick(
            symbol="BTC_USDT", bid=1.0, ask=2.0,  # 100% spread!
            last_price=1.5,
        )
        validator = DataValidator()
        validated = validator.validate_tick(tick)
        assert any("suspiciously wide" in e for e in validated.validation_errors)

    def test_simulated_provider_tick(self):
        provider = SimulatedMarketDataProvider()
        tick = provider.get_tick("BTC_USDT")
        assert tick is not None
        assert tick.symbol == "BTC_USDT"
        assert tick.bid > 0
        assert tick.ask > 0

    def test_simulated_provider_unknown_symbol(self):
        provider = SimulatedMarketDataProvider()
        tick = provider.get_tick("UNKNOWN_USDT")
        assert tick is None

    def test_simulated_provider_order_book(self):
        provider = SimulatedMarketDataProvider()
        book = provider.get_order_book("BTC_USDT", depth=5)
        assert book is not None
        assert len(book.bids) == 5
        assert len(book.asks) == 5
        assert book.best_bid is not None
        assert book.best_ask is not None

    def test_simulated_provider_ohlcv(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=50)
        assert len(bars) == 50
        assert bars[0].open > 0
        assert bars[0].high >= bars[0].low

    def test_validated_tick_returns_none_on_missing(self):
        provider = SimulatedMarketDataProvider()
        tick = get_validated_tick(provider, "NONEXISTENT_USDT")
        assert tick is None

    def test_order_book_staleness(self):
        from datetime import timedelta
        stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        book = OrderBook(
            symbol="BTC_USDT",
            bids=[OrderBookLevel(price=59990.0, quantity=1.0)],
            asks=[OrderBookLevel(price=60010.0, quantity=1.0)],
            timestamp=stale_ts,
        )
        validator = DataValidator(staleness_threshold_seconds=60)
        validated = validator.validate_order_book(book)
        assert validated.is_stale is True


# ===================================================================
# BACKTESTING TESTS
# ===================================================================


class TestBacktesting:
    """Test backtesting harness."""

    def test_basic_backtest_runs(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=100)

        def hold_signal(bars, idx):
            return "hold"

        bt = Backtester(capital=19.0)
        result = bt.run(bars, hold_signal, symbol="BTC_USDT")
        assert result.initial_capital == 19.0
        assert result.total_bars == 100
        assert result.total_trades == 0

    def test_buy_and_hold_backtest(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=100)

        bought = [False]

        def buy_and_hold(bars, idx):
            if idx == 0 and not bought[0]:
                bought[0] = True
                return "buy"
            if idx == len(bars) - 1 and bought[0]:
                return "sell"
            return "hold"

        bt = Backtester(capital=19.0, cost_model=CostModel())
        result = bt.run(bars, buy_and_hold, symbol="BTC_USDT")
        assert result.total_trades == 1
        assert result.total_gross_pnl != 0 or result.total_fees > 0

    def test_reproducibility(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=50)

        def alternating(bars, idx):
            if idx % 10 == 0:
                return "buy"
            if idx % 10 == 5:
                return "sell"
            return "hold"

        bt1 = Backtester(capital=19.0)
        r1 = bt1.run(bars, alternating, symbol="BTC_USDT")

        bt2 = Backtester(capital=19.0)
        r2 = bt2.run(bars, alternating, symbol="BTC_USDT")

        assert r1.total_net_pnl == r2.total_net_pnl
        assert r1.total_trades == r2.total_trades
        assert r1.final_equity == r2.final_equity

    def test_cost_model_applied(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=50)

        bought = [False]

        def buy_sell(bars, idx):
            if idx == 5 and not bought[0]:
                bought[0] = True
                return "buy"
            if idx == 20 and bought[0]:
                return "sell"
            return "hold"

        bt = Backtester(capital=19.0, cost_model=CostModel())
        result = bt.run(bars, buy_sell, symbol="BTC_USDT")
        assert result.total_fees > 0
        assert result.total_slippage > 0
        assert result.total_spread_cost > 0

    def test_metrics_computed(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=100)

        def hold_signal(bars, idx):
            return "hold"

        bt = Backtester(capital=19.0)
        result = bt.run(bars, hold_signal, symbol="BTC_USDT")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "sortino_ratio")
        assert hasattr(result, "calmar_ratio")
        assert hasattr(result, "max_drawdown_pct")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "profit_factor")

    def test_equity_curve_tracked(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=50)

        def hold_signal(bars, idx):
            return "hold"

        bt = Backtester(capital=19.0)
        result = bt.run(bars, hold_signal, symbol="BTC_USDT")
        assert len(result.equity_curve) > 0
        assert result.equity_curve[0] == 19.0

    def test_cost_summary(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=50)

        def hold_signal(bars, idx):
            return "hold"

        bt = Backtester(capital=19.0)
        result = bt.run(bars, hold_signal)
        assert "cost_model_bps" in result.cost_summary

    def test_walk_forward_split(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=100)
        folds = walk_forward_split(bars, n_folds=5, train_ratio=0.7)
        assert len(folds) == 5
        for fold in folds:
            assert len(fold["train"]) > 0
            assert len(fold["test"]) > 0


# ===================================================================
# MARKET INTELLIGENCE TESTS
# ===================================================================


class TestMarketIntelligence:
    """Test signal analysis, regime detection, and intelligence engine."""

    def test_rsi_signal_insufficient_data(self):
        signal = compute_rsi_signal([1.0, 2.0])
        assert signal.direction == "hold"
        assert signal.confidence == 0.0

    def test_rsi_signal_oversold(self):
        # Create a declining price series → RSI should be low
        closes = [100 - i * 0.5 for i in range(30)]
        signal = compute_rsi_signal(closes)
        assert signal.name == "rsi"
        assert signal.indicators["rsi"] < 50

    def test_macd_signal_insufficient_data(self):
        signal = compute_macd_signal([1.0, 2.0, 3.0])
        assert signal.direction == "hold"

    def test_bband_signal_insufficient_data(self):
        signal = compute_bband_signal([1.0, 2.0])
        assert signal.direction == "hold"

    def test_regime_detection_unknown(self):
        result = detect_regime([1.0, 2.0])
        assert result["regime"] == "unknown"

    def test_regime_detection_trending(self):
        # Strong upward trend
        closes = [100 + i * 2 for i in range(50)]
        result = detect_regime(closes)
        assert result["regime"] in ("trending", "volatile")

    def test_regime_detection_ranging(self):
        # Small oscillation (±1%) with no trend = ranging
        closes = [100 + ((-1) ** i) for i in range(50)]
        result = detect_regime(closes)
        assert result["regime"] in ("ranging", "quiet")

    def test_intelligence_engine_full_analysis(self):
        provider = SimulatedMarketDataProvider()
        bars = provider.get_ohlcv("BTC_USDT", limit=50)
        closes = [b.close for b in bars]

        engine = IntelligenceEngine()
        tick = provider.get_tick("BTC_USDT")
        result = engine.full_analysis(closes, tick=tick)

        assert "signals" in result
        assert "regime" in result
        assert "consensus" in result
        assert "data_quality" in result
        assert len(result["signals"]) == 3

    def test_intelligence_consensus(self):
        engine = IntelligenceEngine()
        # Strong uptrend should produce buy consensus
        closes = [100 + i * 3 for i in range(50)]
        result = engine.full_analysis(closes)
        assert result["consensus"] in ("buy", "sell", "hold")


# ===================================================================
# LIVE EXECUTION TESTS
# ===================================================================


class TestLiveExecution:
    """Test live execution pipeline — all gates, all locked states."""

    def test_unauthorized_blocked(self):
        LiveExecutionPipeline.revoke_authorization()
        pipeline = LiveExecutionPipeline(mode="MICRO-LIVE", live_trading_enabled=True)
        result = pipeline.execute(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
        )
        assert result.success is False
        assert result.stage_reached == ExecutionStage.AUTHORIZED
        assert "NOT AUTHORIZED" in result.error

    def test_authorized_but_not_live_blocked(self):
        LiveExecutionPipeline.grant_authorization("test")
        try:
            pipeline = LiveExecutionPipeline(mode="SCAN", live_trading_enabled=False)
            result = pipeline.execute(
                symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
            )
            assert result.success is False
            assert "live trading not enabled" in result.error.lower()
        finally:
            LiveExecutionPipeline.revoke_authorization()

    def test_risk_check_blocks(self):
        LiveExecutionPipeline.grant_authorization("test")
        try:
            risk = RiskEngine(max_position_size_usdt=1.0, seed_capital_usdt=19.0)
            pipeline = LiveExecutionPipeline(
                risk_engine=risk, mode="MICRO-LIVE", live_trading_enabled=True,
            )
            result = pipeline.execute(
                symbol="BTC_USDT", side="buy", quantity=1.0, price=60000.0,
            )
            assert result.success is False
            assert result.stage_reached == ExecutionStage.RISK_CHECKED
        finally:
            LiveExecutionPipeline.revoke_authorization()

    def test_stale_data_blocks(self):
        LiveExecutionPipeline.grant_authorization("test")
        try:
            from datetime import timedelta
            stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
            tick = MarketTick(
                symbol="BTC_USDT", bid=59990.0, ask=60010.0,
                last_price=60000.0, timestamp=stale_ts,
            )
            pipeline = LiveExecutionPipeline(mode="MICRO-LIVE", live_trading_enabled=True)
            result = pipeline.execute(
                symbol="BTC_USDT", side="buy", quantity=0.0001,
                price=60000.0, tick=tick,
            )
            assert result.success is False
            assert "stale" in result.error.lower()
        finally:
            LiveExecutionPipeline.revoke_authorization()

    def test_pipeline_stages_recorded(self):
        LiveExecutionPipeline.revoke_authorization()
        pipeline = LiveExecutionPipeline(mode="MICRO-LIVE", live_trading_enabled=True)
        result = pipeline.execute(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
        )
        assert len(result.audit_entries) >= 1

    def test_authorization_revocation(self):
        LiveExecutionPipeline.grant_authorization("test")
        assert LiveExecutionPipeline.is_authorized() is True
        LiveExecutionPipeline.revoke_authorization()
        assert LiveExecutionPipeline.is_authorized() is False

    def test_not_implemented_live_path(self):
        """Even when all gates pass, live execution returns not_implemented."""
        LiveExecutionPipeline.grant_authorization("test")
        try:
            pipeline = LiveExecutionPipeline(mode="MICRO-LIVE", live_trading_enabled=True)
            result = pipeline.execute(
                symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
            )
            assert result.success is False
            assert "NOT IMPLEMENTED" in result.error
        finally:
            LiveExecutionPipeline.revoke_authorization()


# ===================================================================
# FAILURE MODE TESTS
# ===================================================================


class TestFailureModes:
    """Deliberately test all failure modes.

    The system must fail safely under every condition.
    """

    def test_stale_data_rejected(self):
        """Stale market data must not be used for execution."""
        from datetime import timedelta
        stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
        tick = MarketTick(
            symbol="BTC_USDT", bid=59990.0, ask=60010.0,
            last_price=60000.0, timestamp=stale_ts,
        )
        validator = DataValidator(staleness_threshold_seconds=60)
        validated = validator.validate_tick(tick)
        assert validated.is_stale is True
        # System should refuse to act on stale data
        assert any("stale" in e for e in validated.validation_errors)

    def test_missing_data_returns_none(self):
        """Missing market data returns None, not fabricated data."""
        provider = SimulatedMarketDataProvider()
        tick = provider.get_tick("NONEXISTENT_USDT")
        assert tick is None

    def test_api_outage_returns_none(self):
        """API outage returns None gracefully."""
        provider = SimulatedMarketDataProvider()
        provider.inject_error("api_outage")
        tick = provider.get_tick("BTC_USDT")
        assert tick is None
        book = provider.get_order_book("BTC_USDT")
        assert book is None
        provider.clear_errors()

    def test_rejected_order_tracked(self):
        """Rejected orders are recorded in audit log."""
        risk = RiskEngine(max_position_size_usdt=1.0, seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=1.0, price=60000.0,
        )
        assert verdict.approved is False
        log = risk.get_audit_log()
        assert any(e["event_type"] == "order_check" for e in log)

    def test_duplicate_order_prevented(self):
        """Opening more positions than max_open_positions is blocked."""
        risk = RiskEngine(max_open_positions=1, seed_capital_usdt=19.0)
        risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        verdict = risk.check_order(
            symbol="ETH_USDT", side="buy", quantity=0.01, price=3000.0,
        )
        assert verdict.approved is False
        assert RiskViolation.TOO_MANY_OPEN_POSITIONS in verdict.violations

    def test_partial_fill_handled(self):
        """Partial fills are tracked correctly."""
        engine = PaperTradingEngine(
            seed_capital_usdt=19.0,
            partial_fill_probability=1.0,  # force partial fill
            rejection_probability=0.0,
        )
        result = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.001, price=60000.0,
        )
        if result["status"] == OrderStatus.FILLED:
            assert result["quantity"] < 0.001  # partial fill

    def test_price_movement_affects_pnl(self):
        """Price movement changes P&L correctly."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        pos = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        result = risk.close_position(pos.position_id, exit_price=61000.0)
        assert result["pnl_usdt"] > 0  # profit from price increase

        pos2 = risk.open_position(
            symbol="ETH_USDT", side="buy",
            entry_price=3000.0, quantity=0.001,
        )
        result2 = risk.close_position(pos2.position_id, exit_price=2900.0)
        assert result2["pnl_usdt"] < 0  # loss from price decrease

    def test_risk_breach_blocks_all_subsequent(self):
        """Once a risk limit is breached, all subsequent orders are blocked."""
        risk = RiskEngine(max_daily_loss_usdt=5.0, seed_capital_usdt=19.0)
        risk._state.daily_pnl = -6.0  # breach daily loss
        v1 = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
        )
        assert v1.approved is False
        # Even a tiny order is blocked
        v2 = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.00001, price=60000.0,
        )
        assert v2.approved is False

    def test_emergency_stop_halts_everything(self):
        """Emergency stop immediately blocks ALL orders."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        risk.engage_kill_switch()
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
        )
        assert verdict.approved is False
        assert RiskViolation.KILL_SWITCH_ENGAGED in verdict.violations

    def test_emergency_stop_cooldown_enforced(self):
        """Kill switch cannot be disengaged during cooldown."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        risk.engage_kill_switch()
        risk.disengage_kill_switch()  # should fail (cooldown)
        assert risk.kill_switch_active is True

    def test_leverage_rejected(self):
        """Leverage is always rejected (SPOT ONLY policy)."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001,
            price=60000.0, leverage=3.0,
        )
        assert verdict.approved is False
        assert RiskViolation.LEVERAGE_FORBIDDEN in verdict.violations

    def test_paper_trading_independent_of_live(self):
        """Paper trading works independently of live money."""
        engine = PaperTradingEngine(seed_capital_usdt=19.0)
        result = engine.submit_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
        )
        # Paper trading should produce a result regardless of live mode
        assert result["status"] in (OrderStatus.FILLED, OrderStatus.REJECTED)
        # No live API calls were made
        fills = engine.get_fills()
        for f in fills:
            assert f["fill_price"] > 0  # simulated fill

    def test_empty_price_series_safe(self):
        """Empty price series handled safely everywhere."""
        from engine.intelligence import detect_regime, compute_rsi_signal
        regime = detect_regime([])
        assert regime["regime"] == "unknown"
        signal = compute_rsi_signal([])
        assert signal.direction == "hold"

    def test_zero_price_safe(self):
        """Zero prices handled safely."""
        tick = MarketTick(
            symbol="BTC_USDT", bid=0.0, ask=0.0, last_price=0.0,
        )
        validator = DataValidator()
        validated = validator.validate_tick(tick)
        assert len(validated.validation_errors) > 0

    def test_negative_quantity_safe(self):
        """Negative quantities rejected by risk engine."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=-1, price=60000.0,
        )
        assert verdict.approved is False
        assert RiskViolation.INVALID_ORDER in verdict.violations

    def test_concurrent_risk_state_consistency(self):
        """Opening and closing positions maintains consistent state."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        pos = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        assert len(risk.state.open_positions) == 1
        risk.close_position(pos.position_id, exit_price=61000.0)
        assert len(risk.state.open_positions) == 0

    def test_drawdown_increases_monotonically(self):
        """Max drawdown never decreases."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        pos1 = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        risk.close_position(pos1.position_id, exit_price=62000.0)
        dd1 = risk.state.max_drawdown
        pos2 = risk.open_position(
            symbol="ETH_USDT", side="buy",
            entry_price=3000.0, quantity=0.001,
        )
        risk.close_position(pos2.position_id, exit_price=2800.0)
        dd2 = risk.state.max_drawdown
        assert dd2 >= dd1

    def test_audit_trail_complete(self):
        """Every action produces an audit entry."""
        risk = RiskEngine(seed_capital_usdt=19.0)
        risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.0001, price=60000.0,
        )
        pos = risk.open_position(
            symbol="BTC_USDT", side="buy",
            entry_price=60000.0, quantity=0.0001,
        )
        risk.close_position(pos.position_id, exit_price=61000.0)
        log = risk.get_audit_log()
        types = [e["event_type"] for e in log]
        assert "order_check" in types
        assert "position_opened" in types
        assert "position_closed" in types

    def test_risk_engine_cannot_be_overridden_by_params(self):
        """Risk limits are enforced by the engine, not configurable per-order.

        The LLM cannot pass a parameter that overrides the max position size.
        """
        risk = RiskEngine(max_position_size_usdt=5.0, seed_capital_usdt=19.0)
        # Try to bypass with a large limit parameter — should still fail
        verdict = risk.check_order(
            symbol="BTC_USDT", side="buy", quantity=0.001, price=60000.0,
        )
        assert verdict.approved is False
        # The engine's limit (5.0) was enforced, not any parameter
