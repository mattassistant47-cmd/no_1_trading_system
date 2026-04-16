"""
Performance Tracking & Analytics Engine

Track per-strategy and portfolio-level performance metrics with rolling window
calculations, regime analysis, and automated reporting.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import statistics
from loguru import logger


class MarketRegime(str, Enum):
    """Market regime types"""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    strategy_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Returns
    total_return_pct: float = 0.0
    daily_return_pct: float = 0.0
    annual_return_pct: float = 0.0

    # Risk metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    volatility_pct: float = 0.0

    # Trade metrics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0

    # Efficiency
    trades_total: int = 0
    trades_winning: int = 0
    avg_trade_duration_hours: float = 0.0

    # Risk-adjusted
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0


@dataclass
class PortfolioMetrics:
    """Portfolio-level metrics"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    total_return_pct: float = 0.0
    daily_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    volatility_pct: float = 0.0
    correlation_avg: float = 0.0
    diversification_ratio: float = 0.0
    aggregate_alpha: float = 0.0


class PerformanceTracker:
    """
    Comprehensive performance tracking and analytics for strategies.

    Tracks:
    - Per-strategy metrics: returns, Sharpe, Sortino, max drawdown, win rate, profit factor
    - Portfolio metrics: total return, alpha, beta, information ratio
    - Rolling window calculations (7d, 30d, 90d)
    - Regime performance analysis
    - Metric storage and reporting
    """

    def __init__(
        self,
        risk_free_rate: float = 0.02,
        benchmark_returns: Optional[List[float]] = None,
    ):
        """
        Initialize PerformanceTracker.

        Args:
            risk_free_rate: Annual risk-free rate for Sharpe calculation
            benchmark_returns: Optional benchmark returns for alpha/beta
        """
        self.risk_free_rate = risk_free_rate
        self.benchmark_returns = benchmark_returns or []

        # Storage
        self.strategy_metrics: Dict[str, List[PerformanceMetrics]] = {}
        self.portfolio_metrics: List[PortfolioMetrics] = []
        self.trades: Dict[str, List[Dict]] = {}
        self.drawdown_history: Dict[str, List[float]] = {}
        self.return_history: Dict[str, List[float]] = {}

        logger.info(f"PerformanceTracker initialized with risk_free_rate={risk_free_rate}")

    async def record_trade(
        self,
        strategy_id: str,
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: int,
        entry_time: datetime,
        exit_time: datetime,
        pnl: float,
        pnl_pct: float,
    ):
        """Record a completed trade"""
        if strategy_id not in self.trades:
            self.trades[strategy_id] = []

        trade = {
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "duration": (exit_time - entry_time).total_seconds() / 3600,  # hours
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "winning": pnl > 0,
        }

        self.trades[strategy_id].append(trade)
        logger.debug(
            f"Trade recorded: {strategy_id} {symbol} {quantity} "
            f"${entry_price:.2f}→${exit_price:.2f} PnL=${pnl:.2f}"
        )

    async def update_metrics(
        self,
        strategy_id: str,
        returns: List[float],
        drawdowns: List[float],
        benchmark_returns: Optional[List[float]] = None,
    ) -> PerformanceMetrics:
        """
        Calculate and record performance metrics.

        Args:
            strategy_id: Strategy identifier
            returns: Daily returns
            drawdowns: Daily drawdowns
            benchmark_returns: Benchmark returns for alpha/beta

        Returns:
            PerformanceMetrics
        """
        if strategy_id not in self.strategy_metrics:
            self.strategy_metrics[strategy_id] = []

        # Calculate metrics
        metrics = await self._calculate_metrics(
            strategy_id, returns, drawdowns, benchmark_returns
        )

        self.strategy_metrics[strategy_id].append(metrics)
        self.return_history.setdefault(strategy_id, []).extend(returns)
        self.drawdown_history.setdefault(strategy_id, []).extend(drawdowns)

        logger.info(
            f"Metrics updated for {strategy_id}: "
            f"Sharpe={metrics.sharpe_ratio:.2f}, "
            f"return={metrics.total_return_pct:.2f}%, "
            f"max_dd={metrics.max_drawdown_pct:.2f}%"
        )

        return metrics

    async def _calculate_metrics(
        self,
        strategy_id: str,
        returns: List[float],
        drawdowns: List[float],
        benchmark_returns: Optional[List[float]] = None,
    ) -> PerformanceMetrics:
        """Calculate performance metrics"""
        if not returns:
            return PerformanceMetrics(strategy_id=strategy_id)

        # Return metrics
        total_return = self._calculate_return(returns)
        daily_return = returns[-1] if returns else 0.0
        annual_return = self._annualize_return(returns)

        # Risk metrics
        volatility = self._calculate_volatility(returns)
        sharpe = self._calculate_sharpe(returns, self.risk_free_rate)
        sortino = self._calculate_sortino(returns, self.risk_free_rate)
        max_dd = min(drawdowns) if drawdowns else 0.0

        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0.0

        # Trade metrics
        strategy_trades = self.trades.get(strategy_id, [])
        win_rate = await self._calculate_win_rate(strategy_trades)
        profit_factor = await self._calculate_profit_factor(strategy_trades)
        (avg_win, avg_loss, consec_wins, consec_losses
         ) = await self._calculate_trade_stats(strategy_trades)

        # Risk-adjusted metrics
        alpha, beta = await self._calculate_alpha_beta(
            returns, benchmark_returns or self.benchmark_returns
        )
        info_ratio = self._calculate_information_ratio(
            returns, benchmark_returns or self.benchmark_returns
        )

        # Trade duration
        avg_duration = 0.0
        if strategy_trades:
            avg_duration = statistics.mean(t["duration"] for t in strategy_trades)

        return PerformanceMetrics(
            strategy_id=strategy_id,
            total_return_pct=total_return * 100,
            daily_return_pct=daily_return * 100,
            annual_return_pct=annual_return * 100,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd * 100,
            volatility_pct=volatility * 100,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            consecutive_wins=consec_wins,
            consecutive_losses=consec_losses,
            trades_total=len(strategy_trades),
            trades_winning=sum(1 for t in strategy_trades if t["winning"]),
            avg_trade_duration_hours=avg_duration,
            alpha=alpha,
            beta=beta,
            information_ratio=info_ratio,
        )

    async def get_rolling_metrics(
        self,
        strategy_id: str,
        window_days: int = 30,
    ) -> Optional[PerformanceMetrics]:
        """Get rolling window metrics"""
        if strategy_id not in self.return_history:
            return None

        returns = self.return_history[strategy_id][-window_days:]
        drawdowns = self.drawdown_history[strategy_id][-window_days:]

        if not returns:
            return None

        return await self._calculate_metrics(strategy_id, returns, drawdowns)

    async def get_regime_performance(
        self,
        strategy_id: str,
    ) -> Dict[MarketRegime, PerformanceMetrics]:
        """Analyze performance by market regime"""
        returns = self.return_history.get(strategy_id, [])
        drawdowns = self.drawdown_history.get(strategy_id, [])

        if not returns or len(returns) < 20:
            return {}

        # Classify regimes based on returns
        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0

        regime_returns = {
            MarketRegime.BULL: [],
            MarketRegime.BEAR: [],
            MarketRegime.SIDEWAYS: [],
        }

        regime_drawdowns = {
            MarketRegime.BULL: [],
            MarketRegime.BEAR: [],
            MarketRegime.SIDEWAYS: [],
        }

        for ret, dd in zip(returns, drawdowns):
            if ret > mean_return + std_return:
                regime = MarketRegime.BULL
            elif ret < mean_return - std_return:
                regime = MarketRegime.BEAR
            else:
                regime = MarketRegime.SIDEWAYS

            regime_returns[regime].append(ret)
            regime_drawdowns[regime].append(dd)

        # Calculate metrics for each regime
        regime_metrics = {}
        for regime in MarketRegime:
            if regime_returns[regime]:
                metrics = await self._calculate_metrics(
                    strategy_id, regime_returns[regime], regime_drawdowns[regime]
                )
                regime_metrics[regime] = metrics

        return regime_metrics

    async def get_portfolio_metrics(
        self,
        strategy_allocations: Dict[str, float],
        portfolio_returns: List[float],
    ) -> PortfolioMetrics:
        """Calculate portfolio-level metrics"""
        if not portfolio_returns:
            return PortfolioMetrics()

        # Calculate portfolio metrics
        total_return = self._calculate_return(portfolio_returns)
        annual_return = self._annualize_return(portfolio_returns)
        daily_return = portfolio_returns[-1] if portfolio_returns else 0.0
        volatility = self._calculate_volatility(portfolio_returns)
        sharpe = self._calculate_sharpe(portfolio_returns, self.risk_free_rate)

        # Max drawdown
        drawdown = 0.0
        peak = 0.0
        max_dd = 0.0
        for ret in portfolio_returns:
            peak = max(peak, peak * (1 + ret))
            dd = (peak - peak * (1 + ret)) / peak if peak > 0 else 0.0
            max_dd = min(max_dd, dd)

        # Correlation and diversification
        correlation_avg = await self._calculate_avg_correlation(strategy_allocations)
        diversification_ratio = await self._calculate_diversification_ratio(
            strategy_allocations
        )

        # Aggregate alpha
        aggregate_alpha = sum(
            alloc * (self.strategy_metrics.get(sid, [{}])[-1].alpha or 0.0)
            for sid, alloc in strategy_allocations.items()
        )

        return PortfolioMetrics(
            total_return_pct=total_return * 100,
            daily_return_pct=daily_return * 100,
            annual_return_pct=annual_return * 100,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd * 100,
            volatility_pct=volatility * 100,
            correlation_avg=correlation_avg,
            diversification_ratio=diversification_ratio,
            aggregate_alpha=aggregate_alpha,
        )

    # Helper calculations
    def _calculate_return(self, returns: List[float]) -> float:
        """Calculate cumulative return"""
        if not returns:
            return 0.0

        cum_return = 1.0
        for ret in returns:
            cum_return *= (1 + ret)

        return cum_return - 1.0

    def _calculate_volatility(self, returns: List[float]) -> float:
        """Calculate volatility (standard deviation of returns)"""
        if len(returns) < 2:
            return 0.0

        return statistics.stdev(returns)

    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) < 2:
            return 0.0

        mean_return = statistics.mean(returns)
        volatility = self._calculate_volatility(returns)

        if volatility == 0:
            return 0.0

        # Annualize (assuming daily returns)
        sharpe = (mean_return - risk_free_rate / 252) / volatility
        return sharpe * (252 ** 0.5)

    def _calculate_sortino(self, returns: List[float], risk_free_rate: float) -> float:
        """Calculate Sortino ratio (downside risk only)"""
        if len(returns) < 2:
            return 0.0

        mean_return = statistics.mean(returns)
        downside_returns = [r for r in returns if r < 0]

        if not downside_returns:
            return 0.0

        downside_variance = statistics.variance(downside_returns)
        downside_dev = downside_variance ** 0.5

        if downside_dev == 0:
            return 0.0

        sortino = (mean_return - risk_free_rate / 252) / downside_dev
        return sortino * (252 ** 0.5)

    def _annualize_return(self, returns: List[float]) -> float:
        """Annualize return (assumes daily returns)"""
        if not returns:
            return 0.0

        cum_return = self._calculate_return(returns)
        years = len(returns) / 252  # Trading days per year

        if years <= 0:
            return 0.0

        return (1 + cum_return) ** (1 / years) - 1

    def _calculate_information_ratio(
        self, returns: List[float], benchmark_returns: List[float]
    ) -> float:
        """Calculate information ratio vs benchmark"""
        if not returns or not benchmark_returns or len(returns) != len(benchmark_returns):
            return 0.0

        excess_returns = [r - b for r, b in zip(returns, benchmark_returns)]

        if len(excess_returns) < 2:
            return 0.0

        mean_excess = statistics.mean(excess_returns)
        tracking_error = statistics.stdev(excess_returns)

        if tracking_error == 0:
            return 0.0

        return mean_excess / tracking_error * (252 ** 0.5)

    async def _calculate_alpha_beta(
        self, returns: List[float], benchmark_returns: List[float]
    ) -> Tuple[float, float]:
        """Calculate alpha and beta vs benchmark"""
        if not returns or not benchmark_returns or len(returns) < 2:
            return 0.0, 1.0

        if len(returns) != len(benchmark_returns):
            min_len = min(len(returns), len(benchmark_returns))
            returns = returns[-min_len:]
            benchmark_returns = benchmark_returns[-min_len:]

        # Simple calculation
        mean_return = statistics.mean(returns)
        mean_bench = statistics.mean(benchmark_returns)

        cov = statistics.mean((r - mean_return) * (b - mean_bench)
                             for r, b in zip(returns, benchmark_returns))
        bench_var = statistics.variance(benchmark_returns) if len(benchmark_returns) > 1 else 1.0

        beta = cov / bench_var if bench_var != 0 else 1.0
        alpha = (mean_return * 252) - (0.02 + beta * (mean_bench * 252 - 0.02))

        return alpha, beta

    async def _calculate_avg_correlation(
        self, strategy_allocations: Dict[str, float]
    ) -> float:
        """Calculate average correlation between strategies"""
        strategies = list(strategy_allocations.keys())

        if len(strategies) < 2:
            return 0.0

        # Simplified: would compute actual correlations in production
        return 0.3  # Placeholder

    async def _calculate_diversification_ratio(
        self, strategy_allocations: Dict[str, float]
    ) -> float:
        """Calculate diversification ratio"""
        if not strategy_allocations:
            return 0.0

        # Simplified: true measure is weighted avg volatility / portfolio volatility
        return sum(strategy_allocations.values()) / len(strategy_allocations)

    async def _calculate_win_rate(self, trades: List[Dict]) -> float:
        """Calculate win rate"""
        if not trades:
            return 0.0

        winning = sum(1 for t in trades if t["winning"])
        return winning / len(trades)

    async def _calculate_profit_factor(self, trades: List[Dict]) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        if not trades:
            return 0.0

        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))

        if gross_loss == 0:
            return 0.0 if gross_profit == 0 else float('inf')

        return gross_profit / gross_loss

    async def _calculate_trade_stats(
        self, trades: List[Dict]
    ) -> Tuple[float, float, int, int]:
        """Calculate average win/loss and consecutive wins/losses"""
        if not trades:
            return 0.0, 0.0, 0, 0

        winning_trades = [t["pnl"] for t in trades if t["winning"]]
        losing_trades = [t["pnl"] for t in trades if not t["winning"]]

        avg_win = statistics.mean(winning_trades) if winning_trades else 0.0
        avg_loss = statistics.mean(losing_trades) if losing_trades else 0.0

        # Consecutive wins/losses
        consec_wins = 0
        consec_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in trades[-20:]:  # Last 20 trades
            if trade["winning"]:
                current_wins += 1
                current_losses = 0
                consec_wins = max(consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                consec_losses = max(consec_losses, current_losses)

        return avg_win, avg_loss, consec_wins, consec_losses

    def get_performance_report(self, strategy_id: str) -> Dict:
        """Generate performance report for strategy"""
        metrics_list = self.strategy_metrics.get(strategy_id, [])

        if not metrics_list:
            return {"error": f"No metrics for {strategy_id}"}

        latest = metrics_list[-1]

        return {
            "strategy_id": strategy_id,
            "timestamp": latest.timestamp.isoformat(),
            "returns": {
                "total_pct": latest.total_return_pct,
                "daily_pct": latest.daily_return_pct,
                "annual_pct": latest.annual_return_pct,
            },
            "risk": {
                "sharpe_ratio": latest.sharpe_ratio,
                "sortino_ratio": latest.sortino_ratio,
                "calmar_ratio": latest.calmar_ratio,
                "max_drawdown_pct": latest.max_drawdown_pct,
                "volatility_pct": latest.volatility_pct,
            },
            "trading": {
                "win_rate": latest.win_rate,
                "profit_factor": latest.profit_factor,
                "avg_win": latest.avg_win,
                "avg_loss": latest.avg_loss,
                "consecutive_wins": latest.consecutive_wins,
                "consecutive_losses": latest.consecutive_losses,
                "total_trades": latest.trades_total,
                "winning_trades": latest.trades_winning,
                "avg_duration_hours": latest.avg_trade_duration_hours,
            },
            "risk_adjusted": {
                "alpha": latest.alpha,
                "beta": latest.beta,
                "information_ratio": latest.information_ratio,
            },
        }
