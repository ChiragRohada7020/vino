"""
Unit Tests for Willy Indicator
================================
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import sys
sys.path.insert(0, '..')

from src.willy import calculate_willy, detect_willy_zone, detect_willy_signal


class TestCalculateWilly:
    def create_test_dataframe(self, periods=50, base_price=100.0):
        dates = [datetime(2026, 9, 1) + timedelta(days=i) for i in range(periods)]
        np.random.seed(42)
        data = {
            'datetime': dates,
            'open': [base_price + np.random.normal(0, 1) for _ in range(periods)],
            'high': [base_price + abs(np.random.normal(0, 2)) for _ in range(periods)],
            'low': [base_price - abs(np.random.normal(0, 2)) for _ in range(periods)],
            'close': [base_price + np.random.normal(0, 1) for _ in range(periods)],
            'volume': [100000 + int(np.random.uniform(-50000, 50000)) for _ in range(periods)]
        }
        for i in range(periods):
            if data['high'][i] < data['low'][i]:
                data['high'][i], data['low'][i] = data['low'][i], data['high'][i]
            if data['close'][i] > data['high'][i]:
                data['high'][i] = data['close'][i]
            if data['close'][i] < data['low'][i]:
                data['low'][i] = data['close'][i]
        return pd.DataFrame(data)

    def test_basic_calculation(self):
        df = self.create_test_dataframe(periods=50)
        result = calculate_willy(df, length=21, ema_length=13)
        assert 'willy_upper' in result.columns
        assert 'willy_lower' in result.columns
        assert 'willy' in result.columns
        assert 'willy_ema' in result.columns

    def test_upper_is_rolling_max(self):
        df = self.create_test_dataframe(periods=50)
        result = calculate_willy(df, length=21, ema_length=13)
        # rolling(window=21) includes current row + 20 previous rows
        for i in range(21, 50):
            expected_upper = df['high'].iloc[i-20:i+1].max()
            assert abs(result['willy_upper'].iloc[i] - expected_upper) < 0.01

    def test_lower_is_rolling_min(self):
        df = self.create_test_dataframe(periods=50)
        result = calculate_willy(df, length=21, ema_length=13)
        # rolling(window=21) includes current row + 20 previous rows
        for i in range(21, 50):
            expected_lower = df['low'].iloc[i-20:i+1].min()
            assert abs(result['willy_lower'].iloc[i] - expected_lower) < 0.01

    def test_willy_formula(self):
        df = self.create_test_dataframe(periods=50)
        result = calculate_willy(df, length=21, ema_length=13)
        i = 30
        close = df['close'].iloc[i]
        upper = result['willy_upper'].iloc[i]
        lower = result['willy_lower'].iloc[i]
        if upper != lower:
            expected_willy = 100.0 * (close - upper) / (upper - lower)
            assert abs(result['willy'].iloc[i] - expected_willy) < 0.01

    def test_insufficient_data_raises_error(self):
        df = self.create_test_dataframe(periods=10)
        with pytest.raises(ValueError, match="Insufficient data"):
            calculate_willy(df, length=21, ema_length=13)

    def test_missing_columns_raises_error(self):
        df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        with pytest.raises(ValueError, match="missing required columns"):
            calculate_willy(df, length=21, ema_length=13)

    def test_division_by_zero_handled(self):
        dates = [datetime(2026, 9, 1) + timedelta(days=i) for i in range(50)]
        data = {
            'datetime': dates,
            'open': [100.0] * 50,
            'high': [100.0] * 50,
            'low': [100.0] * 50,
            'close': [100.0] * 50,
            'volume': [100000] * 50
        }
        df = pd.DataFrame(data)
        result = calculate_willy(df, length=21, ema_length=13)
        assert (result['willy'] == 0).all()

    def test_custom_lengths(self):
        df = self.create_test_dataframe(periods=100)
        result = calculate_willy(df, length=10, ema_length=5)
        assert 'willy' in result.columns
        assert 'willy_ema' in result.columns


class TestDetectWillyZone:
    def test_overbought(self):
        assert detect_willy_zone(-10) == 'Overbought'
        assert detect_willy_zone(-20) == 'Overbought'
        assert detect_willy_zone(0) == 'Overbought'

    def test_oversold(self):
        assert detect_willy_zone(-90) == 'Oversold'
        assert detect_willy_zone(-80) == 'Oversold'
        assert detect_willy_zone(-100) == 'Oversold'

    def test_neutral(self):
        assert detect_willy_zone(-50) == 'Neutral'
        assert detect_willy_zone(-30) == 'Neutral'
        assert detect_willy_zone(-70) == 'Neutral'

    def test_nan_input(self):
        assert detect_willy_zone(float('nan')) == 'Unknown'


class TestDetectWillySignal:
    def test_bullish_cross(self):
        result = detect_willy_signal(-50, -60, -70, -60)
        assert result == 'Bullish Cross'

    def test_bearish_cross(self):
        result = detect_willy_signal(-70, -60, -50, -60)
        assert result == 'Bearish Cross'

    def test_no_signal(self):
        result = detect_willy_signal(-50, -60, -55, -60)
        assert result == 'No Signal'

    def test_nan_input(self):
        result = detect_willy_signal(float('nan'), -60, -70, -60)
        assert result == 'No Signal'
