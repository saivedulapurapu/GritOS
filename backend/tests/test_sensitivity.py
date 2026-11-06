"""Fix 1: shock sensitivity = months of runway lost / total shock %, runways capped at 12."""
import pytest

from fragility_model import get_shock_sensitivity, SENSITIVITY_HORIZON_MONTHS


def test_horizon_is_twelve_months():
    assert SENSITIVITY_HORIZON_MONTHS == 12.0


def test_no_shock_is_zero():
    assert get_shock_sensitivity(10, 10, 0) == 0


def test_finite_runways():
    # lost = 10 - 4 = 6 months; total shock 30  ->  6 / 30 = 0.2
    assert get_shock_sensitivity(10, 4, 30) == pytest.approx(0.2)


def test_infinite_baseline_is_capped_at_horizon():
    # baseline None (no burn) -> 12; lost = 12 - 2.5 = 9.5; 9.5 / 100 = 0.095
    assert get_shock_sensitivity(None, 2.5, 100) == pytest.approx(0.095)


def test_both_infinite_is_zero():
    # still no burn after the shock -> nothing lost
    assert get_shock_sensitivity(None, None, 50) == 0


def test_both_beyond_horizon_is_zero():
    # min(20, 12) - min(15, 12) = 12 - 12 = 0
    assert get_shock_sensitivity(20, 15, 10) == 0


def test_runway_improvement_is_not_negative():
    # 4 -> 6 months is a gain, not a loss -> 0
    assert get_shock_sensitivity(4, 6, 50) == 0


def test_rounded_to_three_dp():
    # lost = 10 - 9 = 1; 1 / 3 = 0.3333...  ->  0.333
    assert get_shock_sensitivity(10, 9, 3) == 0.333
