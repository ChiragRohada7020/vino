"""
Unit Tests for Stock Scanner
==============================
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta

import sys
sys.path.insert(0, '..')

from src.scanner import find_nearest_pivot, scan_stock_for_date, run_scanner, ScanResult
from src.pivots import calculate_traditional_pivots
from src.candles import create_sample_ohlc_data, create_intraday_ohlc_data


class TestFindNearestPivot:
    def test_exact_match(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        result = find_nearest_pivot(current_price=90.0, pivot_levels=pivots, max_distance_percent=5.0)
        assert result is not None
        assert result[0] == 'P'
        assert result[2] == 0.0
        assert result[3] == 0.0

    def test_near_pivot_within_threshold(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        result = find_nearest_pivot(current_price=90.1, pivot_levels=pivots, max_distance_percent=5.0)
        assert result is not None
        assert result[0] == 'P'
        assert abs(result[3] - 0.111) < 0.01

    def test_far_from_all_pivots(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        result = find_nearest_pivot(current_price=200.0, pivot_levels=pivots, max_distance_percent=0.5)
        assert result is None

    def test_nearest_to_support(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        result = find_nearest_pivot(current_price=70.2, pivot_levels=pivots, max_distance_percent=5.0)
        assert result is not None
        assert result[0] == 'S2'

    def test_nearest_to_resistance(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        result = find_nearest_pivot(current_price=109.8, pivot_levels=pivots, max_distance_percent=5.0)
        assert result is not None
        assert result[0] == 'R2'

    def test_zero_pivot_price_skipped(self):
        pivots = {'P': 0, 'R1': 100, 'S1': -10}
        result = find_nearest_pivot(current_price=99.5, pivot_levels=pivots, max_distance_percent=5.0)
        assert result is not None
        assert result[0] == 'R1'


class TestScanStockForDate:
    def test_basic_scan(self):
        daily_ohlc = {'high': 825, 'low': 815, 'close': 820}
        intraday_df = create_intraday_ohlc_data(
            symbol='SBIN',
            trading_date=date(2026, 9, 1),
            timeframe_minutes=5,
            base_price=820
        )
        result = scan_stock_for_date(
            stock_symbol='SBIN',
            daily_ohlc=daily_ohlc,
            intraday_df=intraday_df,
            timeframe='5m',
            scan_date=date(2026, 9, 1),
            max_distance_percent=1.0,
            scan_mode='pivot_willy'
        )
        if result is not None:
            assert isinstance(result, ScanResult)
            assert result.stock == 'SBIN'
            assert result.timeframe == '5m'

    def test_empty_dataframe_returns_none(self):
        daily_ohlc = {'high': 825, 'low': 815, 'close': 820}
        empty_df = pd.DataFrame()
        result = scan_stock_for_date(
            stock_symbol='SBIN',
            daily_ohlc=daily_ohlc,
            intraday_df=empty_df,
            timeframe='5m',
            scan_date=date(2026, 9, 1)
        )
        assert result is None

    def test_invalid_daily_ohlc_returns_none(self):
        daily_ohlc = {}
        intraday_df = create_intraday_ohlc_data(base_price=820)
        result = scan_stock_for_date(
            stock_symbol='SBIN',
            daily_ohlc=daily_ohlc,
            intraday_df=intraday_df,
            timeframe='5m',
            scan_date=date(2026, 9, 1)
        )
        assert result is None


class TestRunScanner:
    def test_run_scanner_with_sample_data(self):
        stocks_data = {}
        symbols = ['SBIN', 'RELIANCE', 'TCS']
        for symbol in symbols:
            daily_df = create_sample_ohlc_data(symbol=symbol, periods=60)
            if daily_df is not None and len(daily_df) > 0:
                last = daily_df.iloc[-1]
                stocks_data[symbol] = {
                    'daily_ohlc': {
                        'high': last['high'],
                        'low': last['low'],
                        'close': last['close']
                    },
                    'candles_5m': create_intraday_ohlc_data(
                        symbol=symbol,
                        trading_date=date(2026, 9, 1),
                        timeframe_minutes=5,
                        base_price=last['close']
                    )
                }
        results = run_scanner(
            stocks_data=stocks_data,
            scan_date=date(2026, 9, 1),
            timeframes=['5m'],
            max_distance_percent=5.0,
            scan_mode='pivot_willy'
        )
        assert isinstance(results, list)

    def test_results_sorted_by_distance(self):
        stocks_data = {}
        stocks_data['CLOSE'] = {
            'daily_ohlc': {'high': 100.1, 'low': 99.9, 'close': 100.0},
            'candles_5m': pd.DataFrame({
                'datetime': [datetime(2026, 9, 1, 9, 15)],
                'open': [100.0],
                'high': [100.0],
                'low': [100.0],
                'close': [100.01],
                'volume': [1000]
            })
        }
        stocks_data['FAR'] = {
            'daily_ohlc': {'high': 101, 'low': 99, 'close': 100.0},
            'candles_5m': pd.DataFrame({
                'datetime': [datetime(2026, 9, 1, 9, 15)],
                'open': [100.0],
                'high': [100.0],
                'low': [100.0],
                'close': [100.5],
                'volume': [1000]
            })
        }
        results = run_scanner(
            stocks_data=stocks_data,
            scan_date=date(2026, 9, 1),
            timeframes=['5m'],
            max_distance_percent=1.0,
            scan_mode='pivot'
        )
        if len(results) >= 2:
            assert results[0].distance_percent <= results[1].distance_percent
