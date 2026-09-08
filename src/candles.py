"""
Candle Data Handler
====================

Handles fetching, processing, and caching of OHLC candle data.
Supports both historical and intraday data for any date.
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import date, datetime, timedelta
import os
import json

from .config import CACHE_DIR, CACHE_EXPIRY_HOURS

logger = logging.getLogger(__name__)


def create_sample_ohlc_data(
    symbol: str = 'SBIN',
    start_date: date = None,
    periods: int = 100,
    base_price: float = 800.0
) -> pd.DataFrame:
    """
    Create sample OHLC data for testing purposes.

    Generates realistic-looking OHLC data with random price movements.

    Parameters
    ----------
    symbol : str
        Stock symbol (for reference)
    start_date : date
        Starting date for the data
    periods : int
        Number of candles to generate
    base_price : float
        Starting base price

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: datetime, open, high, low, close, volume
    """
    if start_date is None:
        start_date = date(2026, 8, 1)

    np.random.seed(42)  # For reproducible results

    dates = []
    current_date = datetime.combine(start_date, datetime.min.time().replace(hour=9, minute=15))

    # Generate daily candles
    for i in range(periods):
        # Skip weekends
        while current_date.weekday() >= 5:
            current_date += timedelta(days=1)

        # Random price movement
        change_pct = np.random.normal(0, 0.02)  # 2% std dev
        open_price = base_price * (1 + np.random.normal(0, 0.005))
        close_price = open_price * (1 + change_pct)
        high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.005)))
        low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.005)))
        volume = int(np.random.uniform(100000, 1000000))

        dates.append({
            'datetime': current_date,
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': volume
        })

        base_price = close_price
        current_date += timedelta(days=1)

    return pd.DataFrame(dates)


def create_intraday_ohlc_data(
    symbol: str = 'SBIN',
    trading_date: date = None,
    timeframe_minutes: int = 5,
    base_price: float = 800.0
) -> pd.DataFrame:
    """
    Create sample intraday OHLC data for testing.

    Generates intraday candles for a single trading day.

    Parameters
    ----------
    symbol : str
        Stock symbol
    trading_date : date
        Trading date
    timeframe_minutes : int
        Candle timeframe in minutes
    base_price : float
        Opening price

    Returns
    -------
    pd.DataFrame
        DataFrame with intraday OHLC data
    """
    if trading_date is None:
        trading_date = date(2026, 9, 1)

    np.random.seed(42)

    # Market hours: 09:15 to 15:30
    market_open = datetime.combine(trading_date, datetime.min.time().replace(hour=9, minute=15))
    market_close = datetime.combine(trading_date, datetime.min.time().replace(hour=15, minute=30))

    candles = []
    current_time = market_open
    current_price = base_price

    while current_time <= market_close:
        # Random price movement
        change_pct = np.random.normal(0, 0.001)  # Small intraday moves
        open_price = current_price
        close_price = open_price * (1 + change_pct)
        high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.002)))
        low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.002)))
        volume = int(np.random.uniform(10000, 100000))

        candles.append({
            'datetime': current_time,
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': volume
        })

        current_price = close_price
        current_time += timedelta(minutes=timeframe_minutes)

    return pd.DataFrame(candles)


def get_cache_path(symbol: str, timeframe: str, data_date: date) -> str:
    """Get the cache file path for a specific dataset."""
    filename = f"{symbol}_{timeframe}_{data_date.strftime('%Y%m%d')}.parquet"
    return str(CACHE_DIR / filename)


def cache_exists(symbol: str, timeframe: str, data_date: date) -> bool:
    """Check if cached data exists and is not expired."""
    cache_path = get_cache_path(symbol, timeframe, data_date)
    if not os.path.exists(cache_path):
        return False

    # Check expiry
    file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_path))
    if file_age.total_seconds() > CACHE_EXPIRY_HOURS * 3600:
        return False

    return True


def save_to_cache(df: pd.DataFrame, symbol: str, timeframe: str, data_date: date):
    """Save DataFrame to cache."""
    cache_path = get_cache_path(symbol, timeframe, data_date)
    df.to_parquet(cache_path, index=False)


def load_from_cache(symbol: str, timeframe: str, data_date: date) -> Optional[pd.DataFrame]:
    """Load DataFrame from cache."""
    if not cache_exists(symbol, timeframe, data_date):
        return None

    cache_path = get_cache_path(symbol, timeframe, data_date)
    return pd.read_parquet(cache_path)


# ============================================================================
# LIVE DATA (Fyers API) WITH FILE CACHING
# ============================================================================

# How long "today's" cached data stays fresh (seconds). Completed days are
# cached permanently because their candles can never change.
LIVE_CACHE_TTL_SECONDS = 300


def _api_cache_path(fyers_symbol: str, timeframe: str,
                    from_date: date, to_date: date) -> Path:
    """Cache file path for one API history request (symbol/tf/date-range)."""
    safe = fyers_symbol.replace(':', '_').replace('-', '_')
    fname = (f"api_{safe}_{timeframe}_{from_date.strftime('%Y%m%d')}"
             f"_{to_date.strftime('%Y%m%d')}.json")
    return CACHE_DIR / fname


def _cache_is_fresh(cache_file: Path, to_date: date) -> bool:
    """Fresh = permanent for completed days; TTL-limited for live days."""
    if not cache_file.exists():
        return False
    age = datetime.now().timestamp() - cache_file.stat().st_mtime
    if to_date >= date.today():
        return age < LIVE_CACHE_TTL_SECONDS
    return True  # historical day: candles never change


def fetch_candles_from_api(
    symbol: str,
    timeframe: str,
    from_date: date,
    to_date: date,
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLC candles via the Fyers API (with JSON file caching).

    Parameters
    ----------
    symbol : str
        Project symbol (e.g. 'SBIN'); converted to Fyers format internally.
    timeframe : str
        '5m', '15m', '30m', '1h' or '1d'.
    from_date, to_date : date
        Inclusive date range.
    use_cache : bool
        When True, a fresh cached response is returned instead of an API call.

    Returns
    -------
    pd.DataFrame or None
        Columns: datetime, open, high, low, close, volume.
        None when the API call fails (error is logged, never raised).
    """
    from .fyers_api import get_fyers_api           # local import (avoids cycles)
    from .instruments import get_fyers_symbol

    fyers_symbol = get_fyers_symbol(symbol)
    if not fyers_symbol:
        logger.warning('%s not found in instrument list', symbol)
        return None

    cache_file = _api_cache_path(fyers_symbol, timeframe, from_date, to_date)

    if use_cache and _cache_is_fresh(cache_file, to_date):
        try:
            payload = json.loads(cache_file.read_text(encoding='utf-8'))
            return _candles_from_records(payload['candles'])
        except (OSError, ValueError, KeyError) as exc:
            logger.debug('Cache read failed for %s: %s', cache_file.name, exc)

    api = get_fyers_api()
    candle_dicts = api.get_historical_candles(
        fyers_symbol, timeframe, from_date, to_date
    )
    if candle_dicts is None:
        return None

    if use_cache:
        try:
            cache_file.write_text(
                json.dumps({'candles': candle_dicts}, default=str),
                encoding='utf-8',
            )
        except OSError as exc:
            logger.debug('Cache write failed: %s', exc)

    return _candles_from_records(candle_dicts)


def _candles_from_records(records: List[Dict]) -> pd.DataFrame:
    """Convert list of candle dicts (ISO datetimes) to a tz-aware DataFrame."""
    if not records:
        return pd.DataFrame(
            columns=['datetime', 'open', 'high', 'low', 'close', 'volume']
        )
    df = pd.DataFrame(records)
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True).dt.tz_convert(
        'Asia/Kolkata'
    )
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])
    return df.sort_values('datetime').reset_index(drop=True)


def fetch_daily_history_chunked(
    symbol: str,
    from_date: date,
    to_date: date,
    max_chunk_days: int = 300,
    use_cache: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Fetch a long daily history in <=max_chunk_days slices and merge.

    Fyers rejects history requests spanning too far back in one call
    (code -50 'Invalid input' beyond roughly one year), so yearly pivots
    (~560 days of daily candles) must be downloaded chunk-by-chunk.
    Each chunk is still cached individually by fetch_candles_from_api,
    so repeat scans cost zero API calls.

    Returns merged, de-duplicated, time-sorted DataFrame (or None).
    """
    frames: List[pd.DataFrame] = []
    chunk_end = to_date
    while chunk_end >= from_date:
        chunk_start = max(from_date, chunk_end - timedelta(days=max_chunk_days))
        df = fetch_candles_from_api(symbol, '1d', chunk_start, chunk_end,
                                    use_cache=use_cache)
        if df is not None and not df.empty:
            frames.append(df)
        chunk_end = chunk_start - timedelta(days=1)

    if not frames:
        return None
    merged = (
        pd.concat(frames)
        .drop_duplicates(subset='datetime')
        .sort_values('datetime')
        .reset_index(drop=True)
    )
    return merged


def fetch_latest_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch the latest traded price for many symbols in one batched call.

    Returns a dict {project_symbol: ltp}. Symbols that fail are simply
    omitted (errors are logged inside the API client).
    """
    from .fyers_api import get_fyers_api
    from .instruments import get_fyers_symbol

    out: Dict[str, float] = {}
    chunk_size = 40  # keep the query string comfortably below URL limits
    api = get_fyers_api()

    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        fyers_syms = [get_fyers_symbol(s) for s in chunk]
        pairs = [(s, f) for s, f in zip(chunk, fyers_syms) if f]
        if not pairs:
            continue
        quotes = api.get_quotes([f for _, f in pairs])
        if not quotes:
            continue
        # Fyers echoes the full fyers symbol; match it back to project symbol
        by_fyers = {f: s for s, f in pairs}
        for fyers_key, quote in quotes.items():
            base = fyers_key.split(':')[-1]          # 'NSE:SBIN-EQ' -> 'SBIN-EQ'
            proj = by_fyers.get(fyers_key)
            if proj is None:
                # tolerate suffix differences ('SBIN-EQ' vs 'NSE:SBIN-EQ')
                proj = next((s for s, f in pairs
                             if f.split(':')[-1] == base), None)
            if proj and quote.get('lp') is not None:
                try:
                    out[proj] = float(quote['lp'])
                except (TypeError, ValueError):
                    continue
    return out
