"""
Report Generator Agent

Automated generation of daily P&L summaries, weekly performance reports,
and monthly strategy analysis in JSON and optional Discord/email formats.
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from loguru import logger


class ReportType(str, Enum):
    """Report types"""
    DAILY_PNL = "daily_pnl"
    WEEKLY_PERFORMANCE = "weekly_performance"
    MONTHLY_ANALYSIS = "monthly_analysis"


@dataclass
class DailyPnLReport:
    """Daily P&L summary"""
    date: str
    starting_equity: float
    ending_equity: float
    daily_pnl: float
    daily_return_pct: float
    trades_executed: int
    winning_trades: int
    losing_trades: int
    largest_win: float
    largest_loss: float
    positions_open: int
    largest_position: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class WeeklyPerformanceReport:
    """Weekly performance summary"""
    week_start: str
    week_end: str
    weekly_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    trades_executed: int
    win_rate: float
    profit_factor: float
    best_day_pct: float
    worst_day_pct: float
    strategy_performance: Dict[str, Dict[str, float]] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class MonthlyAnalysisReport:
    """Monthly strategy analysis"""
    month: str
    monthly_return_pct: float
    ytd_return_pct: float
    sharpe_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    profit_factor: float
    correlation_avg: float
    strategy_rankings: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ReportGenerator:
    """
    Autonomous report generation agent.

    Capabilities:
    - Daily P&L summaries
    - Weekly performance reports
    - Monthly strategy analysis
    - JSON export for frontend
    - Discord/email delivery
    - Scheduled generation
    """

    def __init__(
        self,
        report_dir: str = "./reports",
    ):
        """
        Initialize ReportGenerator.

        Args:
            report_dir: Directory for storing reports
        """
        self.report_dir = report_dir
        self.report_history: Dict[ReportType, List[Dict]] = {
            ReportType.DAILY_PNL: [],
            ReportType.WEEKLY_PERFORMANCE: [],
            ReportType.MONTHLY_ANALYSIS: [],
        }

        # Callbacks
        self.on_report_generated: Optional[Callable] = None

        logger.info(f"ReportGenerator initialized with report_dir={report_dir}")

    async def generate_daily_pnl_report(
        self,
        portfolio_metrics: Dict[str, Any],
    ) -> DailyPnLReport:
        """
        Generate daily P&L report.

        Args:
            portfolio_metrics: Portfolio metrics dict

        Returns:
            DailyPnLReport
        """
        report = DailyPnLReport(
            date=datetime.utcnow().date().isoformat(),
            starting_equity=portfolio_metrics.get("starting_equity", 0.0),
            ending_equity=portfolio_metrics.get("current_equity", 0.0),
            daily_pnl=portfolio_metrics.get("daily_pnl", 0.0),
            daily_return_pct=portfolio_metrics.get("daily_return_pct", 0.0),
            trades_executed=portfolio_metrics.get("trades_executed", 0),
            winning_trades=portfolio_metrics.get("winning_trades", 0),
            losing_trades=portfolio_metrics.get("losing_trades", 0),
            largest_win=portfolio_metrics.get("largest_win", 0.0),
            largest_loss=portfolio_metrics.get("largest_loss", 0.0),
            positions_open=portfolio_metrics.get("positions_open", 0),
            largest_position=portfolio_metrics.get("largest_position", {}),
        )

        self.report_history[ReportType.DAILY_PNL].append(asdict(report))

        logger.info(
            f"Daily P&L report generated: ${report.daily_pnl:.2f} "
            f"({report.daily_return_pct:+.2f}%)"
        )

        # Publish
        await self._publish_report(ReportType.DAILY_PNL, report)

        return report

    async def generate_weekly_performance_report(
        self,
        week_start: datetime,
        week_end: datetime,
        performance_metrics: Dict[str, Any],
    ) -> WeeklyPerformanceReport:
        """
        Generate weekly performance report.

        Args:
            week_start: Week start date
            week_end: Week end date
            performance_metrics: Performance metrics dict

        Returns:
            WeeklyPerformanceReport
        """
        # Extract strategy performance
        strategy_perf = {}
        for strategy_id, metrics in performance_metrics.get("strategies", {}).items():
            strategy_perf[strategy_id] = {
                "return_pct": metrics.get("return_pct", 0.0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
                "win_rate": metrics.get("win_rate", 0.0),
            }

        report = WeeklyPerformanceReport(
            week_start=week_start.date().isoformat(),
            week_end=week_end.date().isoformat(),
            weekly_return_pct=performance_metrics.get("weekly_return_pct", 0.0),
            sharpe_ratio=performance_metrics.get("sharpe_ratio", 0.0),
            max_drawdown_pct=performance_metrics.get("max_drawdown_pct", 0.0),
            trades_executed=performance_metrics.get("trades_executed", 0),
            win_rate=performance_metrics.get("win_rate", 0.0),
            profit_factor=performance_metrics.get("profit_factor", 0.0),
            best_day_pct=performance_metrics.get("best_day_pct", 0.0),
            worst_day_pct=performance_metrics.get("worst_day_pct", 0.0),
            strategy_performance=strategy_perf,
        )

        self.report_history[ReportType.WEEKLY_PERFORMANCE].append(asdict(report))

        logger.info(
            f"Weekly performance report generated: "
            f"{report.weekly_return_pct:+.2f}% return, "
            f"Sharpe={report.sharpe_ratio:.2f}"
        )

        await self._publish_report(ReportType.WEEKLY_PERFORMANCE, report)

        return report

    async def generate_monthly_analysis_report(
        self,
        month: datetime,
        analysis_metrics: Dict[str, Any],
    ) -> MonthlyAnalysisReport:
        """
        Generate monthly analysis report.

        Args:
            month: Month to analyze
            analysis_metrics: Analysis metrics dict

        Returns:
            MonthlyAnalysisReport
        """
        # Rank strategies by performance
        strategy_rankings = await self._rank_strategies(
            analysis_metrics.get("strategies", {})
        )

        # Generate recommendations
        recommendations = await self._generate_recommendations(
            analysis_metrics,
            strategy_rankings,
        )

        report = MonthlyAnalysisReport(
            month=month.strftime("%Y-%m"),
            monthly_return_pct=analysis_metrics.get("monthly_return_pct", 0.0),
            ytd_return_pct=analysis_metrics.get("ytd_return_pct", 0.0),
            sharpe_ratio=analysis_metrics.get("sharpe_ratio", 0.0),
            calmar_ratio=analysis_metrics.get("calmar_ratio", 0.0),
            max_drawdown_pct=analysis_metrics.get("max_drawdown_pct", 0.0),
            total_trades=analysis_metrics.get("total_trades", 0),
            win_rate=analysis_metrics.get("win_rate", 0.0),
            profit_factor=analysis_metrics.get("profit_factor", 0.0),
            correlation_avg=analysis_metrics.get("correlation_avg", 0.0),
            strategy_rankings=strategy_rankings,
            recommendations=recommendations,
        )

        self.report_history[ReportType.MONTHLY_ANALYSIS].append(asdict(report))

        logger.info(
            f"Monthly analysis report generated for {report.month}: "
            f"{report.monthly_return_pct:+.2f}% return"
        )

        await self._publish_report(ReportType.MONTHLY_ANALYSIS, report)

        return report

    async def _rank_strategies(
        self, strategies: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """Rank strategies by performance"""
        rankings = []

        for strategy_id, metrics in strategies.items():
            score = (
                metrics.get("sharpe_ratio", 0.0) * 0.40 +
                (1.0 - min(1.0, abs(metrics.get("max_drawdown_pct", 0.0)) / 10)) * 0.30 +
                metrics.get("win_rate", 0.0) * 0.20 +
                min(1.0, metrics.get("profit_factor", 0.0) / 2) * 0.10
            )

            rankings.append({
                "strategy_id": strategy_id,
                "rank": 0,  # Will be set below
                "return_pct": metrics.get("return_pct", 0.0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
                "win_rate": metrics.get("win_rate", 0.0),
                "performance_score": score,
            })

        # Sort by score and assign ranks
        rankings.sort(key=lambda x: x["performance_score"], reverse=True)
        for i, ranking in enumerate(rankings):
            ranking["rank"] = i + 1

        return rankings

    async def _generate_recommendations(
        self,
        metrics: Dict[str, Any],
        rankings: List[Dict],
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        # Return-based recommendations
        monthly_return = metrics.get("monthly_return_pct", 0.0)
        if monthly_return < -5:
            recommendations.append(
                "Consider reducing leverage and risk levels. "
                "Recent performance has been weak."
            )
        elif monthly_return > 10:
            recommendations.append(
                "Strong performance this month. Consider maintaining "
                "current allocation strategy."
            )

        # Sharpe ratio recommendations
        sharpe = metrics.get("sharpe_ratio", 0.0)
        if sharpe < 0.5:
            recommendations.append(
                "Risk-adjusted returns are below target. "
                "Review strategy correlation and diversification."
            )

        # Top and bottom performer recommendations
        if rankings:
            top_strategy = rankings[0]["strategy_id"]
            recommendations.append(
                f"Top performer: {top_strategy}. Consider increasing allocation "
                f"by 2-5% subject to risk limits."
            )

            if len(rankings) > 1:
                bottom_strategy = rankings[-1]["strategy_id"]
                if rankings[-1]["performance_score"] < 0.2:
                    recommendations.append(
                        f"Bottom performer: {bottom_strategy}. "
                        f"Consider reducing allocation or disabling strategy."
                    )

        # Volatility recommendations
        max_dd = metrics.get("max_drawdown_pct", 0.0)
        if max_dd < -10:
            recommendations.append(
                f"Max drawdown of {max_dd:.1f}% exceeds target. "
                f"Increase position sizing constraints."
            )

        # Profit factor recommendations
        pf = metrics.get("profit_factor", 1.0)
        if pf < 1.5:
            recommendations.append(
                "Profit factor below target. "
                "Review trade selection criteria and position management."
            )

        return recommendations if recommendations else ["Continue monitoring current strategy."]

    async def _publish_report(
        self,
        report_type: ReportType,
        report: Any,
    ):
        """Publish report to outputs and webhooks"""
        # Save to JSON
        try:
            filename = f"{report_type.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = f"{self.report_dir}/{filename}"

            report_dict = asdict(report) if hasattr(report, "__dataclass_fields__") else report

            with open(filepath, "w") as f:
                json.dump(report_dict, f, indent=2)

            logger.debug(f"Report saved to {filepath}")

        except Exception as e:
            logger.error(f"Error saving report: {e}")

        # Callback
        if self.on_report_generated:
            await self._safe_call(self.on_report_generated, report_type, report)

    async def _safe_call(self, callback: Callable, *args, **kwargs):
        """Safely call callback"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Callback error: {e}")

    def get_latest_daily_report(self) -> Optional[Dict]:
        """Get latest daily P&L report"""
        reports = self.report_history[ReportType.DAILY_PNL]
        return reports[-1] if reports else None

    def get_latest_weekly_report(self) -> Optional[Dict]:
        """Get latest weekly performance report"""
        reports = self.report_history[ReportType.WEEKLY_PERFORMANCE]
        return reports[-1] if reports else None

    def get_latest_monthly_report(self) -> Optional[Dict]:
        """Get latest monthly analysis report"""
        reports = self.report_history[ReportType.MONTHLY_ANALYSIS]
        return reports[-1] if reports else None

    def get_report_history(
        self,
        report_type: ReportType,
        limit: int = 20,
    ) -> List[Dict]:
        """Get report history"""
        reports = self.report_history[report_type]
        return reports[-limit:] if limit else reports

    def export_all_reports(self) -> Dict[str, List[Dict]]:
        """Export all reports"""
        return self.report_history.copy()
