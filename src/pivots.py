"""
Traditional Pivot Points Calculator
====================================

Calculates Traditional Pivot Points using the previous trading day's
High, Low, and Close to determine current support and resistance levels.

Traditional Pivot Point Formulas (verified against TradingView):
    P  = (H + L + C) / 3
    R1 = 2P - L
    R2 = P + (H - L)
    R3 = H + 2(P - L)
    R4 = H + 3(P - L)        # = R3 + (P - L)
    R5 = H + 4(P - L)        # = R4 + (P - L)
    S1 = 2P - H
    S2 = P - (H - L)
    S3 = L - 2(H - P)
    S4 = L - 3(H - P)        # = S3 - (H - P)
    S5 = L - 4(H - P)        # = S4 - (H - P)

These formulas match TradingView's 'Pivot Points Standard' (Traditional type).
The R4/R5/S4/S5 extension convention was reverse-verified against live chart
data: the August-2026 ONGC monthly candle (H=245.00, L=230.79, C=231.80)
reproduces TradingView's printed labels R1=240.94, R2=250.07, R3=255.15,
R4=260.22, R5=265.29 exactly (see diagnose_ongc_1d.py).
All formulas are configurable via the PIVOT_FORMULAS dictionary.
"""

from typing import Callable, Dict, List, Optional, Tuple

# Configurable pivot formulas
# Each formula is a function that takes (high, low, close, pivot) and returns a float
# This allows easy modification of formulas without changing the main logic

PIVOT_FORMULAS: Dict[str, Dict] = {
    'P': {
        'formula': lambda h, l, c, p: (h + l + c) / 3,
        'description': 'Central Pivot Point - average of H, L, C',
        'needs_pivot': False
    },
    'R1': {
        'formula': lambda h, l, c, p: 2 * p - l,
        'description': 'Resistance 1 - 2x Pivot minus Low',
        'needs_pivot': True
    },
    'R2': {
        'formula': lambda h, l, c, p: p + (h - l),
        'description': 'Resistance 2 - Pivot plus range',
        'needs_pivot': True
    },
    'R3': {
        'formula': lambda h, l, c, p: h + 2 * (p - l),
        'description': 'Resistance 3 - High + 2(Pivot - Low)',
        'needs_pivot': True
    },
    'R4': {
        'formula': lambda h, l, c, p: h + 3 * (p - l),
        'description': 'Resistance 4 - High + 3(Pivot - Low) (TradingView extension)',
        'needs_pivot': True
    },
    'R5': {
        'formula': lambda h, l, c, p: h + 4 * (p - l),
        'description': 'Resistance 5 - High + 4(Pivot - Low) (TradingView extension)',
        'needs_pivot': True
    },
    'S1': {
        'formula': lambda h, l, c, p: 2 * p - h,
        'description': 'Support 1 - 2x Pivot minus High',
        'needs_pivot': True
    },
    'S2': {
        'formula': lambda h, l, c, p: p - (h - l),
        'description': 'Support 2 - Pivot minus range',
        'needs_pivot': True
    },
    'S3': {
        'formula': lambda h, l, c, p: l - 2 * (h - p),
        'description': 'Support 3 - Low - 2(High - Pivot)',
        'needs_pivot': True
    },
    'S4': {
        'formula': lambda h, l, c, p: l - 3 * (h - p),
        'description': 'Support 4 - Low - 3(High - Pivot) (TradingView extension)',
        'needs_pivot': True
    },
    'S5': {
        'formula': lambda h, l, c, p: l - 4 * (h - p),
        'description': 'Support 5 - Low - 4(High - Pivot) (TradingView extension)',
        'needs_pivot': True
    }
}


def calculate_traditional_pivots(
    high: float,
    low: float,
    close: float
) -> Dict[str, float]:
    """
    Calculate all Traditional Pivot Point levels.

    Parameters
    ----------
    high : float
        Previous trading day's high price
    low : float
        Previous trading day's low price
    close : float
        Previous trading day's close price

    Returns
    -------
    Dict[str, float]
        Dictionary with keys: P, R1, R2, R3, R4, R5, S1, S2, S3, S4, S5
        Each value is the corresponding pivot level price

    Raises
    ------
    ValueError
        If any input is negative or invalid
    """
    # Validate inputs
    if any(v < 0 for v in [high, low, close]):
        raise ValueError("High, Low, Close must be non-negative")
    if high < low:
        raise ValueError("High must be >= Low")

    pivots = {}

    # Calculate Pivot Point first (other levels depend on it)
    pivot = (high + low + close) / 3
    pivots['P'] = round(pivot, 2)

    # Calculate all other levels
    for level_name, level_config in PIVOT_FORMULAS.items():
        if level_name == 'P':
            continue  # Already calculated

        formula = level_config['formula']
        if level_config['needs_pivot']:
            pivots[level_name] = round(formula(high, low, close, pivot), 2)
        else:
            pivots[level_name] = round(formula(high, low, close, None), 2)

    return pivots


def get_pivot_levels_list() -> list:
    """
    Get ordered list of pivot level names.

    Returns
    -------
    list
        Ordered list from R5 (highest) to S5 (lowest)
    """
    return ['R5', 'R4', 'R3', 'R2', 'R1', 'P', 'S1', 'S2', 'S3', 'S4', 'S5']


def validate_pivot_symmetry(pivots: Dict[str, float]) -> bool:
    """
    Validate that pivot levels are symmetric around P.

    For Traditional Pivots:
    - R1 - P == P - S1
    - R2 - P == P - S2
    - etc.

    Parameters
    ----------
    pivots : Dict[str, float]
        Dictionary of pivot levels

    Returns
    -------
    bool
        True if symmetric, False otherwise
    """
    p = pivots['P']
    tolerance = 0.01  # Allow small floating point differences

    for i in range(1, 6):
        r_key = f'R{i}'
        s_key = f'S{i}'
        if r_key in pivots and s_key in pivots:
            r_dist = abs(pivots[r_key] - p)
            s_dist = abs(p - pivots[s_key])
            if abs(r_dist - s_dist) > tolerance:
                return False
    return True


# ============================================================================
# MULTI-TIMEFRAME PIVOTS (TradingView D/W/M/Q/Y)
# ============================================================================
#
# TradingView's Pivot Points Standard lets you choose the pivot timeframe:
# Day (D), Week (W), Month (M), Quarter (Q), Year (Y).  The pivots for the
# CURRENT period are computed from the PREVIOUS COMPLETED period's candle:
#     e.g. September's MONTHLY pivots come from August's H/L/C.
#
# Daily candles are aggregated into weekly/monthly/quarterly/yearly candles
# and the previous completed period's H/L/C feeds calculate_traditional_pivots.

import pandas as pd

PIVOT_TIMEFRAMES: List[str] = ['D', 'W', 'M', 'Q', 'Y']

PIVOT_TF_LABELS: Dict[str, str] = {
    'D': 'Daily', 'W': 'Weekly', 'M': 'Monthly', 'Q': 'Quarterly', 'Y': 'Yearly',
    'AUTO': 'Auto (TV: 1m-15m->D, 30m-4h->W, 1d->M)',
}

# TradingView 'Auto' pivot mapping (bucket ranges as shown on live TV charts):
#   1m-15m  -> Daily pivots
#   30m-4h  -> Weekly pivots
#   1d      -> Monthly pivots (1D ONGC chart showed the August monthly set
#              R1=240.94..R5=265.29 - see diagnose_ongc_1d.py)
AUTO_PIVOT_MAP: Dict[str, str] = {
    '1m': 'D', '5m': 'D', '15m': 'D',
    '30m': 'W', '1h': 'W', '2h': 'W', '4h': 'W',
    '1d': 'M',
}

# Calendar days of daily candles needed to cover the previous completed
# period (generous margins so holidays never truncate the period).
PIVOT_TF_FETCH_DAYS: Dict[str, int] = {
    'D': 15,    # previous trading day
    'W': 21,    # previous ISO week (up to ~9 calendar days back, +margin)
    'M': 50,    # previous month (up to 31 days back, +margin)
    'Q': 140,   # previous quarter (up to ~92 days back, +margin)
    'Y': 560,   # previous year (365+ days back, +margin)
}


def days_needed_for_pivot_tf(pivot_tf: str) -> int:
    """Calendar days of daily candles required for a pivot timeframe.

    'all'  -> max over every timeframe (one fetch covers D..Y).
    'auto' -> max over the periods Auto can select (D/W/M -> 50 days)."""
    key = (pivot_tf or 'D').lower()
    if key == 'all':
        return max(PIVOT_TF_FETCH_DAYS.values())
    if key == 'auto':
        return max(PIVOT_TF_FETCH_DAYS[v] for v in AUTO_PIVOT_MAP.values())
    return PIVOT_TF_FETCH_DAYS.get(key.upper(), PIVOT_TF_FETCH_DAYS['D'])


def resolve_pivot_tf(pivot_tf: str, timeframe: str) -> str:
    """Resolve the pivot period for ONE candle timeframe.

    'auto' maps via AUTO_PIVOT_MAP (TradingView rule); explicit D/W/M/Q/Y
    passes through unchanged."""
    ptf = (pivot_tf or 'D').upper()
    if ptf == 'AUTO':
        return AUTO_PIVOT_MAP.get(timeframe, 'D')
    return ptf


def periods_for_pivot_tf(pivot_tf: str, timeframes: List[str]) -> List[str]:
    """Deduped list of pivot periods a scan needs for the given timeframes."""
    ptf = (pivot_tf or 'D').lower()
    if ptf == 'all':
        return list(PIVOT_TIMEFRAMES)
    if ptf == 'auto':
        out: List[str] = []
        for tf in timeframes:
            r = AUTO_PIVOT_MAP.get(tf, 'D')
            if r not in out:
                out.append(r)
        return out or ['D']
    return [ptf.upper()]


def _period_key(d: pd.Timestamp, pivot_tf: str) -> Tuple:
    """Bucket key for a date under a pivot timeframe."""
    if pivot_tf == 'W':
        iso = d.isocalendar()
        return (iso.year, iso.week)          # ISO week (Mon-Sun, NSE trades Mon-Fri)
    if pivot_tf == 'M':
        return (d.year, d.month)
    if pivot_tf == 'Q':
        return (d.year, (d.month - 1) // 3 + 1)
    if pivot_tf == 'Y':
        return (d.year,)
    return (d.year, d.month, d.day)          # 'D' - not used for aggregation


def aggregate_daily_candles(daily_df: pd.DataFrame, pivot_tf: str) -> pd.DataFrame:
    """
    Aggregate daily candles into weekly/monthly/quarterly/yearly candles.

    Parameters
    ----------
    daily_df : pd.DataFrame
        Daily candles with columns: datetime (tz-aware), open, high, low,
        close, volume.  Sorted by datetime (or it will be sorted).
    pivot_tf : str
        One of 'W', 'M', 'Q', 'Y'.

    Returns
    -------
    pd.DataFrame
        Columns: period_start, period_end, open, high, low, close, volume
        sorted by period_end.  'close' is the last trading day's close of
        the period; 'high'/'low' are extremes across the whole period.
    """
    if daily_df is None or daily_df.empty:
        return pd.DataFrame(
            columns=['period_start', 'period_end',
                     'open', 'high', 'low', 'close', 'volume'])

    df = daily_df.sort_values('datetime').copy()
    df['_key'] = df['datetime'].apply(lambda d: _period_key(d, pivot_tf))

    rows = []
    for _key, g in df.groupby('_key', sort=True):
        rows.append({
            '_key': _key,
            'period_start': g['datetime'].iloc[0],
            'period_end': g['datetime'].iloc[-1],
            'open': float(g['open'].iloc[0]),
            'high': float(g['high'].max()),
            'low': float(g['low'].min()),
            'close': float(g['close'].iloc[-1]),
            'volume': float(g['volume'].sum()) if 'volume' in g.columns else 0.0,
        })
    return pd.DataFrame(rows).sort_values('period_end').reset_index(drop=True)


def get_pivot_source_ohlc(
    daily_df: pd.DataFrame,
    pivot_tf: str,
    scan_date: date,
) -> Optional[Dict[str, float]]:
    """
    Get the H/L/C of the PREVIOUS COMPLETED period before scan_date.

    Example: scan_date = 2026-09-07, pivot_tf = 'M'
        -> current period = September 2026
        -> source         = August 2026 candle (H/L/C of all August sessions)

    The result feeds directly into calculate_traditional_pivots().

    Returns
    -------
    dict or None
        {'high', 'low', 'close', 'period_start', 'period_end'} or None when
        the daily data does not cover the previous period.
    """
    pivot_tf = pivot_tf.upper()
    if daily_df is None or daily_df.empty:
        return None

    df = daily_df.sort_values('datetime').copy()
    df['day'] = df['datetime'].dt.date
    # safety: never use a candle dated on/after the scan date
    df = df[df['day'] < scan_date]
    if df.empty:
        return None

    if pivot_tf == 'D':
        last = df.iloc[-1]
        return {
            'high': float(last['high']), 'low': float(last['low']),
            'close': float(last['close']),
            'period_start': last['datetime'], 'period_end': last['datetime'],
        }

    agg = aggregate_daily_candles(df, pivot_tf)
    if agg.empty:
        return None

    scan_key = _period_key(pd.Timestamp(scan_date), pivot_tf)
    prior = agg[agg['_key'].apply(lambda k: k < scan_key)]
    if prior.empty:
        return None

    row = prior.iloc[-1]
    return {
        'high': float(row['high']), 'low': float(row['low']),
        'close': float(row['close']),
        'period_start': row['period_start'], 'period_end': row['period_end'],
    }

