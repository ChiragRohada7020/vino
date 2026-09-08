"""
Willy Indicator Calculator
==========================

Calculates the custom Willy indicator matching TradingView Pine Script logic.

Pine Script Reference:
    length = 21
    upper = highest(length)
    lower = lowest(length)
    out = 100 * (close - upper) / (upper - lower)
    out2 = ema(out, 13)

Formula:
    upper = highest HIGH over previous N candles (rolling max)
    lower = lowest LOW over previous N candles (rolling min)
    willy = 100 * (close - upper) / (upper - lower)
    willy_ema = EMA of willy with span M

Note: Willy ranges from -100 to 0 theoretically, but can exceed these bounds
if price moves outside the lookback range.
"""

import pandas as pd
import numpy as np
from typing import Optional


def calculate_willy(
    df: pd.DataFrame,
    length: int = 21,
    ema_length: int = 13
) -> pd.DataFrame:
    """
    Calculate the Willy indicator and its EMA.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with columns: datetime, open, high, low, close, volume
    length : int
        Lookback period for highest high / lowest low (default: 21)
    ema_length : int
        EMA period for smoothing Willy (default: 13)

    Returns
    -------
    pd.DataFrame
        Original DataFrame with added columns:
        - willy_upper: rolling max of high over `length` periods
        - willy_lower: rolling min of low over `length` periods
        - willy: raw Willy value
        - willy_ema: EMA of Willy

    Raises
    ------
    ValueError
        If required columns are missing or insufficient data
    """
    # Validate input
    required_columns = {'high', 'low', 'close'}
    if not required_columns.issubset(df.columns):
        missing = required_columns - set(df.columns)
        raise ValueError(f"DataFrame missing required columns: {missing}")

    if len(df) < length:
        raise ValueError(
            f"Insufficient data: need at least {length} rows, got {len(df)}"
        )

    # Create a copy to avoid modifying the original
    result = df.copy()

    # Calculate rolling highest high and lowest low
    # Using min_periods=1 so we get values even at the start
    # This matches Pine Script's behavior where highest() starts calculating immediately
    result['willy_upper'] = result['high'].rolling(window=length, min_periods=1).max()
    result['willy_lower'] = result['low'].rolling(window=length, min_periods=1).min()

    # Calculate the range (denominator)
    willy_range = result['willy_upper'] - result['willy_lower']

    # Calculate Willy
    # Handle division by zero: when upper == lower, set willy to 0
    # (price is flat, no momentum)
    result['willy'] = np.where(
        willy_range != 0,
        100.0 * (result['close'] - result['willy_upper']) / willy_range,
        0.0
    )

    # Calculate EMA of Willy
    # Using adjust=False to match Pine Script's EMA behavior
    # Pine Script EMA: alpha = 2 / (length + 1), recursive formula
    # pandas ewm(span=13, adjust=False) uses the same recursive approach
    result['willy_ema'] = result['willy'].ewm(span=ema_length, adjust=False).mean()

    return result


def detect_willy_zone(willy_value: float) -> str:
    """
    Classify the Willy value into a zone.

    Parameters
    ----------
    willy_value : float
        Current Willy value

    Returns
    -------
    str
        'Overbought' if willy >= -20
        'Oversold' if willy <= -80
        'Neutral' otherwise
    """
    if pd.isna(willy_value):
        return 'Unknown'
    if willy_value >= -20:
        return 'Overbought'
    elif willy_value <= -80:
        return 'Oversold'
    else:
        return 'Neutral'


def detect_willy_signal(
    current_willy: float,
    current_willy_ema: float,
    previous_willy: float,
    previous_willy_ema: float
) -> str:
    """
    Detect bullish or bearish crossover signals.

    Bullish Cross: Current Willy > Current EMA AND Previous Willy <= Previous EMA
    Bearish Cross: Current Willy < Current EMA AND Previous Willy >= Previous EMA

    Parameters
    ----------
    current_willy : float
        Current Willy value
    current_willy_ema : float
        Current Willy EMA value
    previous_willy : float
        Previous Willy value
    previous_willy_ema : float
        Previous Willy EMA value

    Returns
    -------
    str
        'Bullish Cross', 'Bearish Cross', or 'No Signal'
    """
    if any(pd.isna(v) for v in [current_willy, current_willy_ema, previous_willy, previous_willy_ema]):
        return 'No Signal'

    # Bullish crossover: Willy crosses above its EMA
    if current_willy > current_willy_ema and previous_willy <= previous_willy_ema:
        return 'Bullish Cross'

    # Bearish crossover: Willy crosses below its EMA
    if current_willy < current_willy_ema and previous_willy >= previous_willy_ema:
        return 'Bearish Cross'

    return 'No Signal'
