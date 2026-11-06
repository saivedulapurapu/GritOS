import pytest

from capital_lock import calculate_capital_lock


def test_frontend_defaults_yellow():
    # value = 5,000 units * 400 = 2,000,000
    # days = 5,000 / 100 per day = 50.0  ->  30 < 50 <= 60  ->  YELLOW
    r = calculate_capital_lock(5_000, 400, 100)
    assert r["locked_capital"] == 2_000_000
    assert r["days_to_liquidate"] == 50.0
    assert r["risk_level"] == "YELLOW"
    assert "2,000,000" in r["warning"]


def test_fast_turnover_green():
    # value = 1,000 * 500 = 500,000; days = 1,000 / 50 = 20.0 -> GREEN
    r = calculate_capital_lock(1_000, 500, 50)
    assert r["locked_capital"] == 500_000
    assert r["days_to_liquidate"] == 20.0
    assert r["risk_level"] == "GREEN"
    assert r["warning"] == "Inventory liquidity is healthy."


def test_slow_turnover_red():
    # value = 7,000 * 100 = 700,000; days = 7,000 / 100 = 70.0 -> > 60 -> RED
    r = calculate_capital_lock(7_000, 100, 100)
    assert r["locked_capital"] == 700_000
    assert r["days_to_liquidate"] == 70.0
    assert r["risk_level"] == "RED"
    assert "700,000" in r["warning"]


@pytest.mark.parametrize(
    "units, expected_days, expected_level",
    [
        (3_000, 30.0, "GREEN"),   # 3,000 / 100 = 30 -> not > 30 -> GREEN
        (6_000, 60.0, "YELLOW"),  # 6,000 / 100 = 60 -> not > 60 -> YELLOW
    ],
)
def test_threshold_boundaries_are_exclusive(units, expected_days, expected_level):
    r = calculate_capital_lock(units, 100, 100)
    assert r["days_to_liquidate"] == expected_days
    assert r["risk_level"] == expected_level


def test_zero_velocity_is_guarded():
    # velocity 0 -> stock never sells through -> days None (no ZeroDivisionError) -> RED
    r = calculate_capital_lock(1_000, 100, 0)
    assert r["days_to_liquidate"] is None
    assert r["risk_level"] == "RED"


def test_days_rounded_to_one_dp():
    # 1,000 / 3 = 333.333...  ->  333.3
    r = calculate_capital_lock(1_000, 10, 3)
    assert r["days_to_liquidate"] == 333.3
