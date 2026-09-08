"""
Unit Tests for Traditional Pivot Points
=========================================
"""

import pytest
import sys
sys.path.insert(0, '..')

from src.pivots import (
    calculate_traditional_pivots,
    get_pivot_levels_list,
    validate_pivot_symmetry,
    PIVOT_FORMULAS
)


class TestCalculateTraditionalPivots:
    def test_basic_calculation(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        assert pivots['P'] == 90.0
        assert pivots['R1'] == 100.0
        assert pivots['R2'] == 110.0
        assert pivots['S1'] == 80.0
        assert pivots['S2'] == 70.0

    def test_all_levels_present(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        expected_levels = ['P', 'R1', 'R2', 'R3', 'R4', 'R5', 'S1', 'S2', 'S3', 'S4', 'S5']
        for level in expected_levels:
            assert level in pivots

    def test_pivot_symmetry(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        assert abs((pivots['R1'] - pivots['P']) - (pivots['P'] - pivots['S1'])) < 0.01
        assert abs((pivots['R2'] - pivots['P']) - (pivots['P'] - pivots['S2'])) < 0.01

    def test_resistance_above_pivot(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        assert pivots['R1'] > pivots['P']
        assert pivots['R2'] > pivots['R1']
        assert pivots['R3'] > pivots['R2']

    def test_support_below_pivot(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        assert pivots['S1'] < pivots['P']
        assert pivots['S2'] < pivots['S1']
        assert pivots['S3'] < pivots['S2']

    def test_negative_values_raise_error(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_traditional_pivots(high=-10, low=80, close=90)

    def test_high_less_than_low_raises_error(self):
        with pytest.raises(ValueError, match="High must be >= Low"):
            calculate_traditional_pivots(high=70, low=80, close=90)

    def test_flat_market(self):
        pivots = calculate_traditional_pivots(high=100, low=100, close=100)
        assert pivots['P'] == 100.0
        assert pivots['R1'] == 100.0
        assert pivots['S1'] == 100.0

    def test_known_values_sbin(self):
        pivots = calculate_traditional_pivots(high=825, low=815, close=820)
        assert pivots['P'] == 820.0
        assert pivots['R1'] == 825.0
        assert pivots['S1'] == 815.0
        assert pivots['R2'] == 830.0
        assert pivots['S2'] == 810.0

    def test_tradingview_r4_r5_s4_s5_extension(self):
        """TradingView extension convention:
        R4 = H + 3(P-L), R5 = H + 4(P-L), S4 = L - 3(H-P), S5 = L - 4(H-P)."""
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        # P = 90, P-L = 10, H-P = 10
        assert pivots['R3'] == 120.0
        assert pivots['R4'] == 130.0
        assert pivots['R5'] == 140.0
        assert pivots['S3'] == 60.0
        assert pivots['S4'] == 50.0
        assert pivots['S5'] == 40.0
        # Ordering must hold
        assert pivots['R4'] > pivots['R3'] > pivots['R2']
        assert pivots['R5'] > pivots['R4']
        assert pivots['S4'] < pivots['S3'] < pivots['S2']
        assert pivots['S5'] < pivots['S4']

    def test_ongc_monthly_chart_labels_regression(self):
        """Regression test: TradingView printed these exact labels for ONGC's
        September 2026 MONTHLY pivots (computed from the August 2026 candle:
        H=245.00, L=230.79, C=231.80). The scanner must reproduce them
        to the paisa (TV rounds to 2 decimals). See diagnose_ongc_1d.py."""
        pivots = calculate_traditional_pivots(high=245.00, low=230.79, close=231.80)
        assert round(pivots['P'], 2) == 235.86
        assert round(pivots['R1'], 2) == 240.94
        assert round(pivots['R2'], 2) == 250.07
        assert round(pivots['R3'], 2) == 255.15
        assert round(pivots['R4'], 2) == 260.22
        assert round(pivots['R5'], 2) == 265.29

    def test_validate_symmetry_function(self):
        pivots = calculate_traditional_pivots(high=100, low=80, close=90)
        assert validate_pivot_symmetry(pivots) is True

    def test_get_pivot_levels_list(self):
        levels = get_pivot_levels_list()
        assert levels == ['R5', 'R4', 'R3', 'R2', 'R1', 'P', 'S1', 'S2', 'S3', 'S4', 'S5']


class TestPivotFormulas:
    def test_all_formulas_callable(self):
        for level_name, config in PIVOT_FORMULAS.items():
            assert callable(config['formula'])

    def test_formula_descriptions_present(self):
        for level_name, config in PIVOT_FORMULAS.items():
            assert 'description' in config
            assert len(config['description']) > 0
