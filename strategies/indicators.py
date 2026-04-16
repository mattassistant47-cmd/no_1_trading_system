"""
Pure numpy/pandas technical indicators.
Drop-in replacement for pandas-ta on ARM64/Python 3.11 where pandas-ta is unavailable.
All function signatures match pandas-ta so existing strategy code works unchanged.
"""

import numpy as np
import pandas as pd


def ema(close: pd.Series, length: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing method."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Wilder's smoothing (equivalent to EMA with alpha = 1/length)
    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()

    rs = avg_gain / avg_loss
    result = 100.0 - (100.0 / (1.0 + rs))
    result.iloc[:length] = np.nan
    return result


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """
    Moving Average Convergence Divergence.

    Returns DataFrame with columns:
        MACD_{fast}_{slow}_{signal}   - MACD line
        MACDs_{fast}_{slow}_{signal}  - Signal line
        MACDh_{fast}_{slow}_{signal}  - Histogram
    """
    fast_ema = ema(close, length=fast)
    slow_ema = ema(close, length=slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, length=signal)
    histogram = macd_line - signal_line

    suffix = f"{fast}_{slow}_{signal}"
    return pd.DataFrame(
        {
            f"MACD_{suffix}": macd_line,
            f"MACDs_{suffix}": signal_line,
            f"MACDh_{suffix}": histogram,
        },
        index=close.index,
    )


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.Series:
    """Average True Range using Wilder's smoothing."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing
    result = true_range.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    result.iloc[: length] = np.nan
    return result


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.DataFrame:
    """
    Average Directional Index.

    Returns DataFrame with columns:
        ADX_{length}  - Average Directional Index
        DMP_{length}  - Plus Directional Indicator (+DI)
        DMN_{length}  - Minus Directional Indicator (-DI)
    """
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    # Directional movement
    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)

    # ATR for smoothing
    atr_values = atr(high, low, close, length=length)

    # Wilder's smoothing on DM
    alpha = 1.0 / length
    smooth_plus_dm = plus_dm.ewm(alpha=alpha, min_periods=length, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=alpha, min_periods=length, adjust=False).mean()

    # Directional indicators
    di_plus = 100.0 * smooth_plus_dm / atr_values
    di_minus = 100.0 * smooth_minus_dm / atr_values

    # DX and ADX
    di_sum = di_plus + di_minus
    di_sum = di_sum.replace(0, np.nan)
    dx = 100.0 * (di_plus - di_minus).abs() / di_sum

    adx_values = dx.ewm(alpha=alpha, min_periods=length, adjust=False).mean()

    return pd.DataFrame(
        {
            f"ADX_{length}": adx_values,
            f"DMP_{length}": di_plus,
            f"DMN_{length}": di_minus,
        },
        index=close.index,
    )


def bbands(
    close: pd.Series, length: int = 20, std: float = 2.0
) -> pd.DataFrame:
    """
    Bollinger Bands.

    Returns DataFrame with columns:
        BBU_{length}_{std}  - Upper band
        BBM_{length}_{std}  - Middle band (SMA)
        BBL_{length}_{std}  - Lower band
    """
    mid = close.rolling(window=length).mean()
    rolling_std = close.rolling(window=length).std(ddof=0)

    upper = mid + std * rolling_std
    lower = mid - std * rolling_std

    suffix = f"{length}_{std}"
    return pd.DataFrame(
        {
            f"BBU_{suffix}": upper,
            f"BBM_{suffix}": mid,
            f"BBL_{suffix}": lower,
        },
        index=close.index,
    )
