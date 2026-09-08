"""
Unit Tests for Date/Calendar Functions
========================================
"""

import pytest
from datetime import date, datetime, timedelta

import sys
sys.path.insert(0, '..')

from src.utils import (
    is_trading_day,
    get_previous_trading_day,
    get_next_trading_day,
    get_trading_days_in_range,
    is_market_open,
    parse_date,
    format_ist_datetime,
    NSE_HOLIDAYS_2026,
    IST
)


class TestIsTradingDay:
    def test_weekday_is_trading_day(self):
        assert is_trading_day(date(2026, 9, 1)) is True

    def test_saturday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 9, 5)) is False

    def test_sunday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 9, 6)) is False

    def test_holiday_is_not_trading_day(self):
        assert is_trading_day(date(2026, 1, 26)) is False

    def test_known_holidays(self):
        for holiday in NSE_HOLIDAYS_2026:
            assert is_trading_day(holiday) is False


class TestGetPreviousTradingDay:
    def test_monday_returns_friday(self):
        monday = date(2026, 9, 7)
        prev = get_previous_trading_day(monday)
        assert prev == date(2026, 9, 4)

    def test_tuesday_returns_monday(self):
        tuesday = date(2026, 9, 8)
        prev = get_previous_trading_day(tuesday)
        assert prev == date(2026, 9, 7)


class TestGetNextTradingDay:
    def test_friday_returns_monday(self):
        friday = date(2026, 9, 4)
        next_day = get_next_trading_day(friday)
        assert next_day == date(2026, 9, 7)

    def test_thursday_returns_friday(self):
        thursday = date(2026, 9, 3)
        next_day = get_next_trading_day(thursday)
        assert next_day == date(2026, 9, 4)


class TestGetTradingDaysInRange:
    def test_one_week_range(self):
        start = date(2026, 9, 1)
        end = date(2026, 9, 7)
        trading_days = get_trading_days_in_range(start, end)
        assert len(trading_days) == 5
        assert date(2026, 9, 5) not in trading_days
        assert date(2026, 9, 6) not in trading_days

    def test_empty_range(self):
        start = date(2026, 9, 7)
        end = date(2026, 9, 1)
        trading_days = get_trading_days_in_range(start, end)
        assert len(trading_days) == 0


class TestIsMarketOpen:
    def test_during_market_hours(self):
        market_time = IST.localize(datetime(2026, 9, 1, 10, 0))
        assert is_market_open(market_time) is True

    def test_before_market_open(self):
        early_time = IST.localize(datetime(2026, 9, 1, 8, 0))
        assert is_market_open(early_time) is False

    def test_after_market_close(self):
        late_time = IST.localize(datetime(2026, 9, 1, 16, 0))
        assert is_market_open(late_time) is False

    def test_weekend(self):
        saturday_time = IST.localize(datetime(2026, 9, 5, 10, 0))
        assert is_market_open(saturday_time) is False


class TestParseDate:
    def test_valid_date_string(self):
        result = parse_date('2026-09-01')
        assert result == date(2026, 9, 1)

    def test_invalid_date_format(self):
        with pytest.raises(ValueError):
            parse_date('01-09-2026')

    def test_invalid_date(self):
        with pytest.raises(ValueError):
            parse_date('2026-13-01')


class TestFormatIstDatetime:
    def test_format_naive_datetime(self):
        dt = datetime(2026, 9, 1, 10, 30, 0)
        result = format_ist_datetime(dt)
        assert '2026-09-01' in result
        assert 'IST' in result

    def test_format_aware_datetime(self):
        dt = IST.localize(datetime(2026, 9, 1, 10, 30, 0))
        result = format_ist_datetime(dt)
        assert '2026-09-01' in result
        assert 'IST' in result
