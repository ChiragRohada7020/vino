"""
Utility Functions
=================

Helper functions for date handling, logging, market hours, and NSE calendar.
"""

import os
import logging
from datetime import datetime, timedelta, date
from typing import List, Optional
import pytz

# NSE Market Hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Timezone
IST = pytz.timezone('Asia/Kolkata')

# NSE Holidays for 2026 (update annually)
# Source: NSE India official holiday list
NSE_HOLIDAYS_2026 = [
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 14),   # Holi
    date(2026, 3, 31),   # Id-ul-Fitr
    date(2026, 4, 3),   # Mahavir Jayanti
    date(2026, 4, 14),   # Ambedkar Jayanti
    date(2026, 5, 1),    # May Day
    date(2026, 6, 26),   # Id-ul-Zuha (Bakri Id)
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 21),  # Dussehra
    date(2026, 11, 14),  # Diwali (Laxmi Pujan)
    date(2026, 12, 25),  # Christmas
]


def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    """
    Set up logging configuration.

    Parameters
    ----------
    log_level : str
        Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns
    -------
    logging.Logger
        Configured logger instance
    """
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(
        log_dir,
        f'scanner_{datetime.now(IST).strftime("%Y%m%d")}.log'
    )

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger('nse_scanner')


def is_trading_day(check_date: date) -> bool:
    """
    Check if a given date is a trading day.

    A trading day is a weekday (Mon-Fri) that is not an NSE holiday.

    Parameters
    ----------
    check_date : date
        Date to check

    Returns
    -------
    bool
        True if trading day, False otherwise
    """
    # Check if weekend
    if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check if holiday
    if check_date in NSE_HOLIDAYS_2026:
        return False

    return True


def get_previous_trading_day(from_date: date) -> Optional[date]:
    """
    Get the previous trading day before the given date.

    Parameters
    ----------
    from_date : date
        Reference date

    Returns
    -------
    date or None
        Previous trading date, or None if not found within 30 days
    """
    current = from_date - timedelta(days=1)
    max_lookback = 30

    for _ in range(max_lookback):
        if is_trading_day(current):
            return current
        current -= timedelta(days=1)

    return None


def get_next_trading_day(from_date: date) -> Optional[date]:
    """
    Get the next trading day after the given date.

    Parameters
    ----------
    from_date : date
        Reference date

    Returns
    -------
    date or None
        Next trading date, or None if not found within 30 days
    """
    current = from_date + timedelta(days=1)
    max_lookback = 30

    for _ in range(max_lookback):
        if is_trading_day(current):
            return current
        current += timedelta(days=1)

    return None


def get_trading_days_in_range(start_date: date, end_date: date) -> List[date]:
    """
    Get all trading days within a date range.

    Parameters
    ----------
    start_date : date
        Start of range (inclusive)
    end_date : date
        End of range (inclusive)

    Returns
    -------
    List[date]
        List of trading dates
    """
    trading_days = []
    current = start_date

    while current <= end_date:
        if is_trading_day(current):
            trading_days.append(current)
        current += timedelta(days=1)

    return trading_days


def is_market_open(check_time: datetime = None) -> bool:
    """
    Check if the market is currently open.

    Parameters
    ----------
    check_time : datetime, optional
        Time to check (defaults to current IST time)

    Returns
    -------
    bool
        True if market is open
    """
    if check_time is None:
        check_time = datetime.now(IST)

    # Convert to IST if not already
    if check_time.tzinfo is None:
        check_time = IST.localize(check_time)
    else:
        check_time = check_time.astimezone(IST)

    # Check if trading day
    if not is_trading_day(check_time.date()):
        return False

    # Check market hours
    market_open = check_time.replace(
        hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0
    )
    market_close = check_time.replace(
        hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0
    )

    return market_open <= check_time <= market_close


def parse_date(date_string: str) -> date:
    """
    Parse a date string in YYYY-MM-DD format.

    Parameters
    ----------
    date_string : str
        Date string to parse

    Returns
    -------
    date
        Parsed date

    Raises
    ------
    ValueError
        If date string is invalid
    """
    try:
        return datetime.strptime(date_string, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date_string}. Use YYYY-MM-DD.")


def format_ist_datetime(dt: datetime) -> str:
    """
    Format datetime in IST timezone.

    Parameters
    ----------
    dt : datetime
        Datetime to format

    Returns
    -------
    str
        Formatted string
    """
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime('%Y-%m-%d %H:%M:%S IST')
