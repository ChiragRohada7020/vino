"""
Stock Scanner Module
====================

Main scanning logic that combines pivot points and Willy indicator
to find stocks near pivot levels with optional Willy signals.

Supports scanning for any historical date using the --date parameter.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime
from dataclasses import dataclass

from .pivots import (
    calculate_traditional_pivots,
    get_pivot_levels_list,
    PIVOT_TIMEFRAMES,
    AUTO_PIVOT_MAP,
)
from .candles import calculate_heikin_ashi
from .willy import calculate_willy, detect_willy_zone, detect_willy_signal
from .utils import get_previous_trading_day, is_trading_day, IST


@dataclass
class ScanResult:
    """Data class for a single scan result."""
    stock: str
    timeframe: str
    current_price: float
    nearest_pivot: str
    pivot_price: float
    distance: float
    distance_percent: float
    willy: Optional[float] = None
    willy_ema: Optional[float] = None
    willy_zone: Optional[str] = None
    willy_signal: Optional[str] = None
    last_candle_time: Optional[str] = None
    pivot_tf: str = 'D'   # D/W/M/Q/Y - which period's candle produced the pivots


def find_nearest_pivot(
    current_price: float,
    pivot_levels: Dict[str, float],
    max_distance_percent: float = 0.50
) -> Optional[Tuple[str, float, float, float]]:
    """
    Find the nearest pivot level to the current price.

    Parameters
    ----------
    current_price : float
        Current market price of the stock
    pivot_levels : Dict[str, float]
        Dictionary of pivot levels (P, R1-R5, S1-S5)
    max_distance_percent : float
        Maximum distance percentage threshold (default: 0.50%)

    Returns
    -------
    tuple or None
        (pivot_name, pivot_price, absolute_distance, distance_percent)
        or None if no pivot is within threshold
    """
    nearest = None
    min_distance_pct = float('inf')

    for pivot_name, pivot_price in pivot_levels.items():
        if pivot_price <= 0:
            continue

        abs_distance = abs(current_price - pivot_price)
        pct_distance = (abs_distance / pivot_price) * 100

        if pct_distance < min_distance_pct:
            min_distance_pct = pct_distance
            nearest = (pivot_name, pivot_price, abs_distance, pct_distance)

    if nearest and nearest[3] <= max_distance_percent:
        return nearest

    return None


def scan_stock_for_date(
    stock_symbol: str,
    daily_ohlc: Dict[str, float],
    intraday_df: pd.DataFrame,
    timeframe: str,
    scan_date: date,
    max_distance_percent: float = 0.50,
    scan_mode: str = 'pivot_willy',
    willy_length: int = 21,
    willy_ema_length: int = 13,
    use_heikin_ashi: bool = False,
) -> Optional[ScanResult]:
    """
    Scan a single stock for a specific date.

    Parameters
    ----------
    stock_symbol : str
        Stock symbol (e.g., 'SBIN')
    daily_ohlc : Dict
        Previous trading day's OHLC with keys: high, low, close
    intraday_df : pd.DataFrame
        Intraday candle data up to scan_date
    timeframe : str
        Timeframe string (5m, 15m, 30m, 1h, 1d)
    scan_date : date
        Date to scan for
    max_distance_percent : float
        Maximum distance from pivot threshold
    scan_mode : str
        'pivot' for pivot only, 'pivot_willy' for pivot + willy
    willy_length : int
        Willy lookback period
    willy_ema_length : int
        Willy EMA period

    Returns
    -------
    ScanResult or None
        Scan result if stock is near a pivot, None otherwise
    """
    # Calculate pivot levels from previous day's OHLC
    try:
        pivot_levels = calculate_traditional_pivots(
            daily_ohlc['high'],
            daily_ohlc['low'],
            daily_ohlc['close']
        )
    except (ValueError, KeyError):
        return None

    # Get current price (last candle's close)
    if intraday_df is None or len(intraday_df) == 0:
        return None

    current_price = intraday_df['close'].iloc[-1]

    # Find nearest pivot
    nearest = find_nearest_pivot(current_price, pivot_levels, max_distance_percent)
    if nearest is None:
        return None

    pivot_name, pivot_price, abs_distance, pct_distance = nearest

    # Build result
    result = ScanResult(
        stock=stock_symbol,
        timeframe=timeframe,
        current_price=round(current_price, 2),
        nearest_pivot=pivot_name,
        pivot_price=pivot_price,
        distance=round(abs_distance, 2),
        distance_percent=round(pct_distance, 4),
        last_candle_time=str(intraday_df['datetime'].iloc[-1]) if 'datetime' in intraday_df.columns else None
    )

    # Calculate Willy if mode is pivot_willy
    if scan_mode == 'pivot_willy' and len(intraday_df) >= willy_length:
        try:
            willy_df = calculate_heikin_ashi(intraday_df) if use_heikin_ashi else intraday_df
            df_with_willy = calculate_willy(willy_df, willy_length, willy_ema_length)

            current_willy = df_with_willy['willy'].iloc[-1]
            current_willy_ema = df_with_willy['willy_ema'].iloc[-1]

            result.willy = round(current_willy, 2)
            result.willy_ema = round(current_willy_ema, 2)
            result.willy_zone = detect_willy_zone(current_willy)

            # Detect signal (need previous values)
            if len(df_with_willy) >= 2:
                previous_willy = df_with_willy['willy'].iloc[-2]
                previous_willy_ema = df_with_willy['willy_ema'].iloc[-2]
                result.willy_signal = detect_willy_signal(
                    current_willy, current_willy_ema,
                    previous_willy, previous_willy_ema
                )
        except (ValueError, Exception):
            # Willy calculation failed, but we still have pivot result
            pass

    return result


def run_scanner(
    stocks_data: Dict[str, Dict],
    scan_date: date,
    timeframes: List[str] = None,
    max_distance_percent: float = 0.50,
    scan_mode: str = 'pivot_willy',
    pivot_tf: str = 'D',
    use_heikin_ashi: bool = False,
) -> List[ScanResult]:
    """
    Run the scanner for multiple stocks and timeframes.

    Parameters
    ----------
    stocks_data : Dict
        Dictionary with stock symbols as keys and data as values.
        Each stock may provide:
          - 'daily_ohlc'          : source H/L/C (classic single-period mode)
          - 'daily_ohlc_by_tf'    : {'D'|'W'|'M'|'Q'|'Y': {'high','low','close'}}
                                    (multi-period mode, from get_pivot_source_ohlc)
    scan_date : date
        Date to scan for
    timeframes : List[str]
        List of timeframes to scan
    max_distance_percent : float
        Distance threshold
    scan_mode : str
        Scan mode ('pivot' or 'pivot_willy')
    pivot_tf : str
        Pivot timeframe: 'D', 'W', 'M', 'Q', 'Y', 'all' (scan every period)
        or 'auto' (TradingView-style: intraday timeframes use Daily pivots,
        the 1d timeframe uses Monthly pivots - resolved per result row).

    Returns
    -------
    List[ScanResult]
        List of scan results sorted by distance percentage
    """
    if timeframes is None:
        timeframes = ['5m', '15m', '30m', '1h', '4h', '1d']

    pivot_mode = (pivot_tf or 'D').lower()
    results = []

    for stock_symbol, stock_info in stocks_data.items():
        by_tf = stock_info.get('daily_ohlc_by_tf') or {}
        fallback = stock_info.get('daily_ohlc')

        # Period sources available for this stock
        available = {ptf: by_tf[ptf] for ptf in PIVOT_TIMEFRAMES if by_tf.get(ptf)}
        if not available and fallback:
            available = {'D': fallback}

        for timeframe in timeframes:
            # Which pivot periods apply to THIS candle timeframe?
            if pivot_mode == 'all':
                periods = list(PIVOT_TIMEFRAMES)
            elif pivot_mode == 'auto':
                # TradingView-style auto: intraday -> Daily, 1d -> Monthly
                periods = [AUTO_PIVOT_MAP.get(timeframe, 'D')]
            else:
                periods = [pivot_mode.upper()]

            for ptf in periods:
                daily_ohlc = available.get(ptf)
                if not daily_ohlc:
                    continue
                # pass only what scan_stock_for_date expects
                ohlc = {k: daily_ohlc[k]
                        for k in ('high', 'low', 'close') if k in daily_ohlc}
                if not ohlc:
                    continue

                try:
                    result = scan_stock_for_date(
                        stock_symbol=stock_symbol,
                        daily_ohlc=ohlc,
                        intraday_df=stock_info.get(f'candles_{timeframe}'),
                        timeframe=timeframe,
                        scan_date=scan_date,
                        max_distance_percent=max_distance_percent,
                        scan_mode=scan_mode,
                        use_heikin_ashi=use_heikin_ashi,
                    )
                    if result:
                        result.pivot_tf = ptf
                        results.append(result)
                except Exception as e:
                    # Log error but continue scanning other stocks
                    print(f"Error scanning {stock_symbol} {timeframe}: {e}")
                    continue

    # Sort by distance percentage (ascending - closest first)
    results.sort(key=lambda x: x.distance_percent)

    return results
