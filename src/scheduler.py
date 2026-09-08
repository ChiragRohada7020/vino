"""
Market Session Scheduler
=========================

Handles scheduling of scans around NSE market hours.
Manages pre-market, during-market, and post-market operations.
"""

from datetime import datetime, time, date, timedelta
from typing import Optional
import pytz

from .config import IST
from .utils import is_trading_day, get_next_trading_day, get_previous_trading_day


# NSE Market Hours
MARKET_OPEN = time(9, 15)   # 09:15 AM IST
MARKET_CLOSE = time(15, 30)  # 03:30 PM IST

# Pre-market and post-market windows
PRE_MARKET_START = time(8, 0)    # Start preparing pivots
POST_MARKET_END = time(16, 0)     # End of post-market processing


def get_market_status(check_time: datetime = None) -> str:
    """
    Get current market status.

    Parameters
    ----------
    check_time : datetime, optional
        Time to check (defaults to current IST time)

    Returns
    -------
    str
        One of: 'pre_market', 'open', 'closed', 'post_market', 'holiday'
    """
    if check_time is None:
        check_time = datetime.now(IST)

    # Convert to IST
    if check_time.tzinfo is None:
        check_time = IST.localize(check_time)
    else:
        check_time = check_time.astimezone(IST)

    current_date = check_time.date()
    current_time = check_time.time()

    # Check if trading day
    if not is_trading_day(current_date):
        return 'holiday'

    # Check market hours
    if current_time < MARKET_OPEN:
        return 'pre_market'
    elif MARKET_OPEN <= current_time <= MARKET_CLOSE:
        return 'open'
    elif current_time <= POST_MARKET_END:
        return 'post_market'
    else:
        return 'closed'


def should_calculate_pivots(check_time: datetime = None) -> bool:
    """
    Check if it's time to calculate pivots (pre-market).

    Parameters
    ----------
    check_time : datetime, optional
        Time to check

    Returns
    -------
    bool
        True if pivots should be calculated
    """
    if check_time is None:
        check_time = datetime.now(IST)

    if check_time.tzinfo is None:
        check_time = IST.localize(check_time)
    else:
        check_time = check_time.astimezone(IST)

    current_date = check_time.date()
    current_time = check_time.time()

    # Calculate pivots in pre-market window
    if not is_trading_day(current_date):
        return False

    return PRE_MARKET_START <= current_time < MARKET_OPEN


def should_run_scan(check_time: datetime = None) -> bool:
    """
    Check if scanner should run (during market hours).

    Parameters
    ----------
    check_time : datetime, optional
        Time to check

    Returns
    -------
    bool
        True if scanner should run
    """
    return get_market_status(check_time) == 'open'


def get_next_scan_time() -> Optional[datetime]:
    """
    Get the next time the scanner should run.

    Returns
    -------
    datetime or None
        Next scan time in IST
    """
    now = datetime.now(IST)
    current_status = get_market_status(now)

    if current_status == 'open':
        # Market is open, scan now
        return now
    elif current_status == 'pre_market':
        # Wait for market open
        return datetime.combine(now.date(), MARKET_OPEN, tzinfo=IST)
    elif current_status in ['post_market', 'closed', 'holiday']:
        # Wait for next trading day's market open
        next_day = get_next_trading_day(now.date())
        if next_day:
            return datetime.combine(next_day, MARKET_OPEN, tzinfo=IST)

    return None
