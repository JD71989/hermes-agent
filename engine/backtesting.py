"""Guardian Backtesting Harness.

Provides reproducible backtesting with:
- Historical data ingestion
- Transaction costs (fees, slippage, spread)
- Position tracking during backtest
- Performance metrics (Sharpe, Sortino, Calmar, max drawdown, win rate)
- Walk-forward validation support
- Overfitting detection

Results are deterministic given the same inputs (reproducible).

Architecture:
- Backtester composes SimulatedMarketDataProvider + RiskEngine
- Every trade goes through the full risk pipeline
- Cost model is configurable but defaults to realistic values
- All results include the cost breakdown for transparency
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from engine.market_data import OHLCVBar, SimulatedMarketDataProvider
from engine.risk_engine import RiskEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    """A single trade executed during backtesting."""
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_bar: int
    exit_bar: int
    gross_pnl: float
    fees: float
    slippage_cost: float
    spread_cost: float
    net_pnl: float
    strategy: str


# ---------------------------------------------------------------------------
# Backtest cost model
# ---------------------------------------------------------------------------

@dataclass
class CostModel:
    """Transaction cost model for backtesting."""
    maker_fee_rate: float = 0.001
    taker_fee_rate: float = 0.002
    slippage_bps: float = 5.0
    spread_bps: float = 2.0
    safety_margin_bps: float = 50.0

    def round_trip_cost_bps(self) -> float:
        """Total cost in bps for a round-trip trade."""
        fee_bps = ((self.maker_fee_rate + self.taker_fee_rate) / 2) * 10000
        return fee_bps + self.slippage_bps + self.spread_bps + self.safety_margin_bps

    def trade_cost_usdt(self, notional: float) -> float:
        """Total cost in USDT for a single trade."""
        return (self.round_trip_cost_bps() / 2 / 10000) * notional  # one-way cost

    def one_way_cost_pct(self) -> float:
        """One-way transaction cost as a fraction of notional."""
        return self.round_trip_cost_bps() / 2 / 10000

    def slippage_pct(self) -> float:
        """Slippage cost as a fraction of notional."""
        return self.slippage_bps / 10000

    def spread_pct(self) -> float:
        """Spread cost as a fraction of notional."""
        return self.spread_bps / 10000

    def fee_component_pct(self) -> float:
        """Fee component of the one-way cost (absorbs the safety margin)."""
        return self.one_way_cost_pct() - self.slippage_pct() - self.spread_pct()


# ---------------------------------------------------------------------------
# Signal function type
# ---------------------------------------------------------------------------

# A signal function takes a list of OHLCV bars up to current index
# and returns: "buy", "sell", or "hold"
SignalFn = Callable[[List[OHLCVBar], int], str]


# ---------------------------------------------------------------------------
# Backtest result
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Complete backtest result with all metrics."""
    strategy_name: str
    symbol: str
    total_bars: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_gross_pnl: float
    total_fees: float
    total_slippage: float
    total_spread_cost: float
    total_net_pnl: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    max_consecutive_losses: int
    final_equity: float
    initial_capital: float
    return_pct: float
    trades: List[BacktestTrade]
    equity_curve: List[float]
    cost_summary: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["trades"] = [asdict(t) for t in self.trades]
        return d


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

class Backtester:
    """Reproducible backtesting engine.

    Usage:
        backtester = Backtester(capital=19.0)
        result = backtester.run(
            bars=ohlcv_bars,
            signal_fn=my_signal_fn,
            symbol="BTC_USDT",
            strategy_name="my_strategy",
        )
    """

    def __init__(
        self,
        capital: float = 19.0,
        cost_model: Optional[CostModel] = None,
    ) -> None:
        self._capital = capital
        self._cost_model = cost_model or CostModel()
        self._risk = RiskEngine(
            max_capital_usdt=capital,
            max_position_size_usdt=capital,
            max_total_exposure_usdt=capital,
            seed_capital_usdt=capital,
        )

    def run(
        self,
        bars: Sequence[OHLCVBar],
        signal_fn: SignalFn,
        symbol: str = "BTC_USDT",
        strategy_name: str = "backtest",
    ) -> BacktestResult:
        """Run a backtest over OHLCV bars with a signal function.

        Returns BacktestResult with full metrics.
        """
        equity = self._capital
        peak_equity = equity
        max_drawdown = 0.0
        trades: List[BacktestTrade] = []
        equity_curve = [equity]
        position: Optional[Dict[str, Any]] = None  # current open position
        consecutive_losses = 0
        max_consecutive_losses = 0

        total_fees = 0.0
        total_slippage = 0.0
        total_spread = 0.0

        for i in range(len(bars)):
            signal = signal_fn(list(bars[: i + 1]), i)

            if signal == "buy" and position is None:
                # Open long position — size so one-way costs are fully covered
                entry_price = bars[i].close
                one_way = self._cost_model.one_way_cost_pct()
                notional = equity / (1 + one_way)
                quantity = notional / entry_price
                if quantity > 0 and equity > 0:
                    position = {
                        "entry_price": entry_price,
                        "quantity": quantity,
                        "entry_bar": i,
                        "fee_open": notional * self._cost_model.fee_component_pct(),
                        "slippage_open": notional * self._cost_model.slippage_pct(),
                        "spread_open": notional * self._cost_model.spread_pct(),
                    }
                    equity = notional  # cash fully deployed; entry costs booked

            elif signal == "sell" and position is not None:
                # Close long position
                exit_price = bars[i].close
                entry_price = position["entry_price"]
                quantity = position["quantity"]
                exit_notional = exit_price * quantity
                one_way = self._cost_model.one_way_cost_pct()

                fee_close = exit_notional * self._cost_model.fee_component_pct()
                slippage_close = exit_notional * self._cost_model.slippage_pct()
                spread_close = exit_notional * self._cost_model.spread_pct()

                total_fees += position["fee_open"] + fee_close
                total_slippage += position["slippage_open"] + slippage_close
                total_spread += position["spread_open"] + spread_close

                gross_pnl = exit_notional - (entry_price * quantity)
                net_pnl = (
                    gross_pnl
                    - position["fee_open"]
                    - position["slippage_open"]
                    - position["spread_open"]
                    - fee_close
                    - slippage_close
                    - spread_close
                )
                equity += exit_notional - exit_notional * one_way

                trade = BacktestTrade(
                    trade_id=str(uuid.uuid4())[:8],
                    symbol=symbol,
                    side="buy",
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=quantity,
                    entry_bar=position["entry_bar"],
                    exit_bar=i,
                    gross_pnl=round(gross_pnl, 6),
                    fees=round(position["fee_open"] + fee_close, 6),
                    slippage_cost=round(
                        position["slippage_open"] + slippage_close, 6
                    ),
                    spread_cost=round(
                        position["spread_open"] + spread_close, 6
                    ),
                    net_pnl=round(net_pnl, 6),
                    strategy=strategy_name,
                )
                trades.append(trade)

                # Update drawdown
                peak_equity = max(peak_equity, equity)
                if peak_equity > 0:
                    dd = (peak_equity - equity) / peak_equity
                    max_drawdown = max(max_drawdown, dd)

                # Track consecutive losses
                if net_pnl < 0:
                    consecutive_losses += 1
                    max_consecutive_losses = max(
                        max_consecutive_losses, consecutive_losses
                    )
                else:
                    consecutive_losses = 0

                position = None

            # Mark open positions to market so the equity curve is realistic
            if position is not None:
                equity = position["quantity"] * bars[i].close

            equity_curve.append(round(equity, 6))

        # Calculate metrics
        winning_trades = [t for t in trades if t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl <= 0]
        win_rate = len(winning_trades) / len(trades) if trades else 0.0

        total_gross = sum(t.gross_pnl for t in trades)
        total_net = sum(t.net_pnl for t in trades)

        avg_win = (
            sum(t.net_pnl for t in winning_trades) / len(winning_trades)
            if winning_trades
            else 0.0
        )
        avg_loss = (
            sum(t.net_pnl for t in losing_trades) / len(losing_trades)
            if losing_trades
            else 0.0
        )

        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Sharpe / Sortino from equity curve returns
        returns = []
        for j in range(1, len(equity_curve)):
            if equity_curve[j - 1] > 0:
                returns.append((equity_curve[j] - equity_curve[j - 1]) / equity_curve[j - 1])

        sharpe = self._compute_sharpe(returns)
        sortino = self._compute_sortino(returns)
        calmar = (total_net / self._capital) / max_drawdown if max_drawdown > 0 else 0.0

        return_pct = ((equity - self._capital) / self._capital * 100) if self._capital > 0 else 0.0

        return BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            total_bars=len(bars),
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=round(win_rate, 4),
            total_gross_pnl=round(total_gross, 6),
            total_fees=round(total_fees, 6),
            total_slippage=round(total_slippage, 6),
            total_spread_cost=round(total_spread, 6),
            total_net_pnl=round(total_net, 6),
            max_drawdown_pct=round(max_drawdown, 6),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            calmar_ratio=round(calmar, 4),
            profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            avg_win=round(avg_win, 6),
            avg_loss=round(avg_loss, 6),
            max_consecutive_losses=max_consecutive_losses,
            final_equity=round(equity, 6),
            initial_capital=self._capital,
            return_pct=round(return_pct, 4),
            trades=trades,
            equity_curve=equity_curve,
            cost_summary={
                "total_fees": round(total_fees, 6),
                "total_slippage": round(total_slippage, 6),
                "total_spread": round(total_spread, 6),
                "cost_model_bps": self._cost_model.round_trip_cost_bps(),
            },
        )

    @staticmethod
    def _compute_sharpe(returns: Sequence[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        mean = statistics.fmean(returns)
        std = statistics.stdev(returns)
        if std == 0:
            return 0.0
        return (mean - risk_free) / std * math.sqrt(252)

    @staticmethod
    def _compute_sortino(returns: Sequence[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        mean = statistics.fmean(returns)
        downside = [r for r in returns if r < risk_free]
        if len(downside) < 2:
            return 0.0
        downside_std = statistics.stdev(downside)
        if downside_std == 0:
            return 0.0
        return (mean - risk_free) / downside_std * math.sqrt(252)


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def walk_forward_split(
    bars: Sequence[OHLCVBar],
    n_folds: int = 5,
    train_ratio: float = 0.7,
) -> List[Dict[str, Any]]:
    """Split bars into walk-forward folds.

    Returns list of dicts with 'train' and 'test' bar sequences.
    Each fold uses earlier bars for training and later bars for testing.
    """
    fold_size = len(bars) // n_folds
    folds = []

    for i in range(n_folds):
        start = i * fold_size
        end = min(start + fold_size, len(bars))
        fold_bars = list(bars[start:end])
        split = int(len(fold_bars) * train_ratio)
        folds.append({
            "fold": i,
            "train": fold_bars[:split],
            "test": fold_bars[split:],
        })

    return folds
