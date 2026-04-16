"""
Utility functions for the API.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def calculate_returns(initial_value: float, current_value: float) -> tuple[float, float]:
    """
    Calculate absolute and percentage returns.

    Returns:
        (absolute_return, percentage_return)
    """
    absolute_return = current_value - initial_value
    percentage_return = (absolute_return / initial_value * 100) if initial_value > 0 else 0
    return absolute_return, percentage_return


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe ratio from returns.

    Args:
        returns: List of daily/period returns
        risk_free_rate: Annual risk-free rate (default 2%)

    Returns:
        Sharpe ratio
    """
    if not returns or len(returns) < 2:
        return 0.0

    import statistics

    mean_return = statistics.mean(returns)
    std_dev = statistics.stdev(returns)

    if std_dev == 0:
        return 0.0

    # Annualize for daily returns
    annual_sharpe = (mean_return * 252 - risk_free_rate) / (std_dev * (252**0.5))
    return annual_sharpe


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """
    Calculate maximum drawdown from equity curve.

    Args:
        equity_curve: List of portfolio values over time

    Returns:
        Maximum drawdown as percentage
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0

    max_drawdown = 0.0
    peak = equity_curve[0]

    for value in equity_curve[1:]:
        if value > peak:
            peak = value

        drawdown = (peak - value) / peak * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    return max_drawdown


def calculate_win_rate(trades: List[Dict[str, Any]]) -> float:
    """
    Calculate win rate from trades.

    Args:
        trades: List of trade dictionaries with 'pnl' key

    Returns:
        Win rate as percentage
    """
    if not trades:
        return 0.0

    winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
    return (winning_trades / len(trades) * 100) if trades else 0.0


def calculate_profit_factor(trades: List[Dict[str, Any]]) -> float:
    """
    Calculate profit factor from trades.

    Profit Factor = Gross Profit / Gross Loss

    Args:
        trades: List of trade dictionaries with 'pnl' key

    Returns:
        Profit factor
    """
    if not trades:
        return 0.0

    gross_profit = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
    gross_loss = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))

    if gross_loss == 0:
        return 0.0

    return gross_profit / gross_loss


def paginate(
    items: List[Any],
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[Any], int]:
    """
    Paginate a list of items.

    Args:
        items: List to paginate
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        (paginated_items, total_items)
    """
    total = len(items)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    return items[start_idx:end_idx], total


def format_currency(value: float, decimals: int = 2) -> str:
    """Format value as currency string."""
    return f"${value:,.{decimals}f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format value as percentage string."""
    return f"{value:.{decimals}f}%"


def format_timestamp(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime object."""
    return dt.strftime(format_str)


def parse_timestamp(timestamp_str: str, format_str: str = "%Y-%m-%dT%H:%M:%S") -> datetime:
    """Parse timestamp string to datetime."""
    return datetime.strptime(timestamp_str, format_str)


def get_time_ago(dt: datetime) -> str:
    """Get human-readable relative time."""
    now = datetime.utcnow()
    delta = now - dt

    seconds = delta.total_seconds()

    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    elif seconds < 604800:
        return f"{int(seconds / 86400)}d ago"
    else:
        return f"{int(seconds / 604800)}w ago"


def merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two dictionaries, with updates taking precedence.
    """
    result = base.copy()
    result.update(updates)
    return result


def filter_dict(data: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """Filter dictionary to only include specified keys."""
    return {k: v for k, v in data.items() if k in keys}


def exclude_dict(data: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """Filter dictionary to exclude specified keys."""
    return {k: v for k, v in data.items() if k not in keys}


def round_to_nearest(value: float, nearest: float = 0.01) -> float:
    """Round value to nearest increment."""
    return round(value / nearest) * nearest
