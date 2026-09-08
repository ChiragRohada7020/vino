"""
Unit Tests for Multi-Timeframe Pivot Points (D/W/M/Q/Y)
========================================================

Covers:
    - aggregate_daily_candles()  : daily -> weekly/monthly/quarterly/yearly
    - get_pivot_source_ohlc()    : previous completed period selection
    - run_scanner() multi-period integration via 'daily_ohlc_by_tf'

Includes a regression test locking the scanner to TradingView's printed
ONGC MONTHLY labels (August 2026 candle -> September 2026 pivots).
"""

import pytest
import pandas as pd
from datetime import date

import sys
sys.path.insert(0, '..')

from src.pivots import (
    aggregate_daily_candles,
    get_pivot_source_ohlc,
    calculate_traditional_pivots,
    PIVOT_TIMEFRAMES,
    resolve_pivot_tf,
    periods_for_pivot_tf,
    days_needed_for_pivot_tf,
)
from src.scanner import run_scanner
from src.candles import create_intraday_ohlc_data


def make_daily(rows):
    """Build a daily OHLC DataFrame like fetch_candles_from_api returns.

    rows: list of (year, month, day, open, high, low, close)"""
    data = [{
        'datetime': pd.Timestamp(y, m, d, 15, 30, tz='Asia/Kolkata'),
        'open': float(o), 'high': float(h), 'low': float(l),
        'close': float(c), 'volume': 1000,
    } for (y, m, d, o, h, l, c) in rows]
    return pd.DataFrame(data).sort_values('datetime').reset_index(drop=True)


class TestAggregateDailyCandles:
    def test_monthly_aggregation_basics(self):
        rows = [
            # August: 3 sessions
            (2026, 8, 3, 100, 105, 99, 104),
            (2026, 8, 4, 104, 110, 103, 108),
            (2026, 8, 5, 108, 112, 107, 111),
            # September: 2 sessions
            (2026, 9, 1, 111, 115, 110, 114),
            (2026, 9, 2, 114, 118, 113, 116),
        ]
        agg = aggregate_daily_candles(make_daily(rows), 'M')

        assert len(agg) == 2
        aug, sep = agg.iloc[0], agg.iloc[1]
        # August candle: open = first day's open, high = max, low = min,
        # close = last day's close
        assert aug['open'] == 100.0
        assert aug['high'] == 112.0
        assert aug['low'] == 99.0
        assert aug['close'] == 111.0
        assert sep['open'] == 111.0
        assert sep['high'] == 118.0
        assert sep['low'] == 110.0
        assert sep['close'] == 116.0

    def test_weekly_aggregation_iso_weeks(self):
        rows = [
            # ISO week of Aug 31 - Sep 4 2026
            (2026, 8, 31, 100, 104, 99, 103),
            (2026, 9, 2, 103, 106, 102, 105),
            (2026, 9, 4, 105, 108, 104, 107),
            # next ISO week: Sep 7-8
            (2026, 9, 7, 107, 109, 106, 108),
            (2026, 9, 8, 108, 110, 107, 109),
        ]
        agg = aggregate_daily_candles(make_daily(rows), 'W')
        assert len(agg) == 2
        w1, w2 = agg.iloc[0], agg.iloc[1]
        assert w1['close'] == 107.0
        assert w1['high'] == 108.0
        assert w1['low'] == 99.0
        assert w2['open'] == 107.0
        assert w2['close'] == 109.0

    def test_quarterly_and_yearly_aggregation(self):
        rows = [
            (2025, 11, 3, 90, 95, 89, 94),      # 2025 Q4
            (2026, 1, 5, 94, 99, 93, 98),       # 2026 Q1
            (2026, 4, 1, 98, 103, 97, 102),     # 2026 Q2
            (2026, 7, 1, 102, 107, 101, 106),   # 2026 Q3
        ]
        q = aggregate_daily_candles(make_daily(rows), 'Q')
        assert len(q) == 4                       # 4 distinct quarters
        assert list(q['close']) == [94.0, 98.0, 102.0, 106.0]

        y = aggregate_daily_candles(make_daily(rows), 'Y')
        assert len(y) == 2                       # 2025 + 2026
        y25, y26 = y.iloc[0], y.iloc[1]
        assert y25['high'] == 95.0 and y25['low'] == 89.0
        assert y26['high'] == 107.0 and y26['low'] == 93.0

    def test_empty_dataframe(self):
        agg = aggregate_daily_candles(pd.DataFrame(columns=[
            'datetime', 'open', 'high', 'low', 'close', 'volume']), 'M')
        assert agg.empty


class TestGetPivotSourceOhlc:
    def test_daily_uses_last_completed_day(self):
        rows = [
            (2026, 9, 3, 236, 238, 235, 236),
            (2026, 9, 4, 235, 235.44, 233.60, 234.65),   # last completed
            (2026, 9, 7, 236, 238, 235, 237),            # scan date itself
        ]
        src = get_pivot_source_ohlc(make_daily(rows), 'D', date(2026, 9, 7))
        assert src is not None
        # candle ON the scan date must be excluded
        assert src['high'] == 235.44
        assert src['low'] == 233.60
        assert src['close'] == 234.65

    def test_monthly_ongc_tradingview_regression(self):
        """TradingView prints these MONTHLY pivot labels for ONGC during
        September 2026 (derived from the August 2026 monthly candle:
        H=245.00, L=230.79, C=231.80).  The scanner must reproduce them
        to the paisa.  See diagnose_ongc_1d.py."""
        rows = [
            # August 2026 daily sessions (synthetic, but aggregating to the
            # exact ONGC monthly candle H/L/C)
            (2026, 8, 3, 240, 243, 238, 242),
            (2026, 8, 10, 242, 245.00, 240, 241),
            (2026, 8, 17, 241, 244, 236, 238),
            (2026, 8, 24, 238, 240, 233, 234),
            (2026, 8, 26, 234, 236, 230.79, 232),
            (2026, 8, 28, 232, 234, 231, 233),
            (2026, 8, 31, 233, 235, 231, 231.80),
            # September sessions before the scan date
            (2026, 9, 1, 233, 236, 232, 236),
            (2026, 9, 4, 236, 238, 234, 237),
        ]
        src = get_pivot_source_ohlc(make_daily(rows), 'M', date(2026, 9, 7))
        assert src is not None
        assert src['high'] == 245.00
        assert src['low'] == 230.79
        assert src['close'] == 231.80

        pivots = calculate_traditional_pivots(
            high=src['high'], low=src['low'], close=src['close'])
        assert pivots['P'] == 235.86
        assert pivots['R1'] == 240.94
        assert pivots['R2'] == 250.07
        assert pivots['R3'] == 255.15
        assert pivots['R4'] == 260.22
        assert pivots['R5'] == 265.29

    def test_weekly_uses_previous_iso_week(self):
        rows = [
            (2026, 8, 31, 100, 104, 99, 103),
            (2026, 9, 2, 103, 106, 102, 105),
            (2026, 9, 4, 105, 108, 104, 107),    # prior week's last session
            (2026, 9, 7, 107, 109, 106, 108),    # current week (Mon)
        ]
        src = get_pivot_source_ohlc(make_daily(rows), 'W', date(2026, 9, 9))
        assert src is not None
        assert src['high'] == 108.0
        assert src['low'] == 99.0
        assert src['close'] == 107.0

    def test_quarterly_uses_previous_quarter(self):
        rows = [
            (2026, 4, 6, 98, 103, 97, 102),
            (2026, 5, 11, 102, 106, 100, 105),
            (2026, 6, 30, 105, 110, 104, 109),   # Q2 end
            (2026, 7, 1, 109, 111, 108, 110),    # Q3 first session
        ]
        src = get_pivot_source_ohlc(make_daily(rows), 'Q', date(2026, 7, 8))
        assert src is not None
        assert src['high'] == 110.0
        assert src['low'] == 97.0
        assert src['close'] == 109.0

    def test_yearly_uses_previous_year(self):
        rows = [
            (2025, 6, 2, 90, 95, 89, 94),
            (2025, 12, 31, 94, 100, 93, 99),     # 2025 end
            (2026, 1, 1, 99, 103, 98, 102),      # 2026 first session
        ]
        src = get_pivot_source_ohlc(make_daily(rows), 'Y', date(2026, 8, 3))
        assert src is not None
        assert src['high'] == 100.0
        assert src['low'] == 89.0
        assert src['close'] == 99.0

    def test_no_prior_period_returns_none(self):
        # only sessions inside the current month -> no completed prior month
        rows = [(2026, 9, 1, 100, 105, 99, 104),
                (2026, 9, 2, 104, 106, 103, 105)]
        assert get_pivot_source_ohlc(make_daily(rows), 'M',
                                     date(2026, 9, 7)) is None

    def test_empty_data_returns_none(self):
        empty = pd.DataFrame(columns=['datetime', 'open', 'high', 'low',
                                      'close', 'volume'])
        for tf in PIVOT_TIMEFRAMES:
            assert get_pivot_source_ohlc(empty, tf, date(2026, 9, 7)) is None


class TestRunScannerMultiTF:
    ONGC_AUG = {'high': 245.00, 'low': 230.79, 'close': 231.80}
    ONGC_SEP4 = {'high': 235.44, 'low': 233.60, 'close': 234.65}

    def _stocks_data(self):
        intraday = create_intraday_ohlc_data(
            symbol='ONGC', trading_date=date(2026, 9, 7),
            timeframe_minutes=5, base_price=233.70)
        return {'ONGC': {
            'daily_ohlc_by_tf': {'M': dict(self.ONGC_AUG),
                                 'D': dict(self.ONGC_SEP4)},
            'candles_5m': intraday,
        }}

    def test_all_scans_every_period(self):
        results = run_scanner(
            stocks_data=self._stocks_data(),
            scan_date=date(2026, 9, 7),
            timeframes=['5m'],
            max_distance_percent=5.0,
            scan_mode='pivot',
            pivot_tf='all',
        )
        tfs = {r.pivot_tf for r in results}
        assert tfs == {'D', 'M'}
        assert all(r.pivot_tf in PIVOT_TIMEFRAMES for r in results)

    def test_monthly_only(self):
        stocks = self._stocks_data()
        results = run_scanner(
            stocks_data=stocks,
            scan_date=date(2026, 9, 7),
            timeframes=['5m'],
            max_distance_percent=5.0,
            scan_mode='pivot',
            pivot_tf='M',
        )
        assert results, 'monthly pivots should produce hits within 5%'
        assert all(r.pivot_tf == 'M' for r in results)
        # cross-check: nearest monthly pivot must match the LAST close of
        # the intraday series (the sample data random-walks, so derive the
        # expectation instead of hard-coding S1)
        pivots = calculate_traditional_pivots(**self.ONGC_AUG)
        last_close = float(stocks['ONGC']['candles_5m']['close'].iloc[-1])
        expected = min(pivots.items(),
                       key=lambda kv: abs(last_close - kv[1]) / kv[1])[0]
        assert all(r.nearest_pivot == expected for r in results)

    def test_classic_mode_still_works(self):
        # legacy stocks_data: only 'daily_ohlc' (no by_tf) -> treated as D
        intraday = create_intraday_ohlc_data(
            symbol='SBIN', trading_date=date(2026, 9, 7),
            timeframe_minutes=5, base_price=820.0)
        stocks = {'SBIN': {
            'daily_ohlc': {'high': 825, 'low': 815, 'close': 820},
            'candles_5m': intraday,
        }}
        results = run_scanner(
            stocks_data=stocks, scan_date=date(2026, 9, 7),
            timeframes=['5m'], max_distance_percent=1.0,
            scan_mode='pivot', pivot_tf='D')
        assert results
        assert all(r.pivot_tf == 'D' for r in results)

    def test_auto_mode_tradingview_mapping(self):
        """TradingView 'Auto': intraday timeframes use DAILY pivots, the
        1d chart uses MONTHLY pivots - resolved independently per row."""
        intraday_5m = create_intraday_ohlc_data(
            symbol='ONGC', trading_date=date(2026, 9, 7),
            timeframe_minutes=5, base_price=233.70)
        intraday_1d = create_intraday_ohlc_data(
            symbol='ONGC', trading_date=date(2026, 9, 7),
            timeframe_minutes=1440, base_price=233.70)
        stocks = {'ONGC': {
            'daily_ohlc_by_tf': {'M': dict(self.ONGC_AUG),
                                 'D': dict(self.ONGC_SEP4)},
            'candles_5m': intraday_5m,
            'candles_1d': intraday_1d,
        }}
        results = run_scanner(
            stocks_data=stocks, scan_date=date(2026, 9, 7),
            timeframes=['5m', '1d'], max_distance_percent=5.0,
            scan_mode='pivot', pivot_tf='auto')
        assert results, 'auto mode should produce hits within 5%'
        by_tf = {}
        for r in results:
            by_tf.setdefault(r.timeframe, set()).add(r.pivot_tf)
        assert by_tf.get('5m') == {'D'}, \
            'intraday rows must use Daily pivots in auto mode'
        assert by_tf.get('1d') == {'M'}, \
            '1d rows must use Monthly pivots in auto mode'


class TestResolvePivotTf:
    """TradingView Auto mapping helpers."""

    def test_auto_bucket_ranges_match_tradingview(self):
        """Full TradingView auto buckets:
        1m-15m -> Daily, 30m-4h -> Weekly, 1d -> Monthly."""
        for tf in ('1m', '5m', '15m'):
            assert resolve_pivot_tf('auto', tf) == 'D', tf
        for tf in ('30m', '1h', '2h', '4h'):
            assert resolve_pivot_tf('auto', tf) == 'W', tf
        assert resolve_pivot_tf('auto', '1d') == 'M'

    def test_auto_daily_chart_maps_to_monthly(self):
        assert resolve_pivot_tf('auto', '1d') == 'M'

    def test_explicit_period_passes_through(self):
        for ptf in ('D', 'W', 'M', 'Q', 'Y'):
            assert resolve_pivot_tf(ptf, '5m') == ptf
            assert resolve_pivot_tf(ptf, '1d') == ptf

    def test_case_insensitive(self):
        assert resolve_pivot_tf('AUTO', '5m') == 'D'
        assert resolve_pivot_tf('Auto', '1d') == 'M'
        assert resolve_pivot_tf(None, '5m') == 'D'   # default

    def test_periods_for_auto_dedupes(self):
        assert periods_for_pivot_tf('auto', ['5m', '15m']) == ['D']
        assert periods_for_pivot_tf('auto', ['5m', '1d']) == ['D', 'M']
        assert periods_for_pivot_tf('auto', ['1d', '1d']) == ['M']

    def test_periods_for_all_and_explicit(self):
        assert periods_for_pivot_tf('all', ['5m']) == list(PIVOT_TIMEFRAMES)
        assert periods_for_pivot_tf('W', ['5m', '1d']) == ['W']

    def test_days_needed_for_auto(self):
        # auto can select D (15d) or M (50d) -> must cover the larger
        assert days_needed_for_pivot_tf('auto') == 50
        assert days_needed_for_pivot_tf('all') == 560
        assert days_needed_for_pivot_tf('D') == 15
