"""Fix 2: runway-decay estimate — λ = runway x tier factor, never more than runway."""
import math

import pytest

from runway_decay import (
    MAX_ESTIMATE,
    calculate_runway_decay_estimate,
    calculate_runway_decay_trajectory,
    effective_runway,
)

TIERS = ["Critical", "Fragile", "Stable", "Resilient"]
estimate = calculate_runway_decay_estimate


# ---------- core requirement: λ <= runway ----------

@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("runway", [0.5, 2.5, 6.0, 12.0, 24.0])
def test_effective_runway_never_exceeds_runway(tier, runway):
    assert effective_runway(runway, tier) <= runway


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("runway", [0.5, 2.5, 6.0, 12.0, 24.0])
def test_estimate_never_beats_face_value_runway(tier, runway):
    # Upper bound: λ = runway itself  ->  exp(-6 / runway). +0.05 allows for 1 dp rounding.
    ceiling = math.exp(-6 / runway) * 100
    assert estimate(runway, tier) <= ceiling + 0.05


# ---------- hand-calculated values ----------

@pytest.mark.parametrize(
    "runway, tier",
    [
        (6.0, "Resilient"),   # λ = 6.0 x 1.0 = 6
        (6.0, "Stable"),      # λ = 6.0 x 1.0 = 6
        (7.5, "Fragile"),     # λ = 7.5 x 0.8 = 6
        (10.0, "Critical"),   # λ = 10 x 0.6 = 6
    ],
)
def test_same_effective_runway_same_estimate(runway, tier):
    # exp(-6 / 6) = exp(-1) = 0.3679 -> 36.8%
    assert estimate(runway, tier) == 36.8


def test_revenue_wipeout_example():
    # λ = 2.5 x 1.0 = 2.5  ->  exp(-6 / 2.5) = exp(-2.4) = 0.0907 -> 9.1%
    assert estimate(2.5, "Resilient") == 9.1


def test_known_conservative_bias_documented_value():
    # Documented in the module docstring: 12-month runway -> exp(-6 / 12) = 60.7% at month 6
    assert estimate(12.0, "Resilient") == 60.7


def test_critical_haircut_lowers_estimate():
    # Critical: λ = 12 x 0.6 = 7.2 -> exp(-6 / 7.2) = 43.5%  (vs 60.7% at face value)
    assert estimate(12.0, "Critical") == 43.5


# ---------- sentinel and edge cases ----------

@pytest.mark.parametrize("tier", TIERS)
def test_no_cash_burn_is_capped_not_certain(tier):
    assert effective_runway(None, tier) is None
    assert estimate(None, tier) == MAX_ESTIMATE == 99.9


def test_zero_runway_is_zero():
    assert estimate(0.0, "Stable") == 0.0


def test_longer_runway_never_lowers_estimate():
    values = [estimate(r, "Fragile") for r in (1, 2, 4, 8, 16, 32)]
    assert values == sorted(values)


# ---------- trajectory ----------

def test_trajectory_shape_and_decay():
    traj = calculate_runway_decay_trajectory(2.5, "Resilient")
    assert [p["name"] for p in traj] == [f"Month {t}" for t in range(1, 7)]
    values = [p["prob"] for p in traj]
    assert values == sorted(values, reverse=True)
    # month 1: exp(-1 / 2.5) = 67.0% ; month 6 equals the 6-month estimate
    assert values[0] == 67.0
    assert values[-1] == estimate(2.5, "Resilient")


def test_trajectory_flat_when_no_burn():
    assert {p["prob"] for p in calculate_runway_decay_trajectory(None, "Stable")} == {99.9}
