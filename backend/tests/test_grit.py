"""Fix 2b: Grit Score — one function for baseline and scenario, documented weights, short-runway cap."""
import pytest

from grit import SHORT_RUNWAY_CAP, compute_grit
from main import FullBusinessState, process_business_state

score = lambda *a: compute_grit(*a)["score"]


# ---------- weights ----------

def test_equal_weights_tier_and_decay():
    # 0.5 x 100 + 0.5 x 60 = 80; no concentration (0%), fast stock (10 days), no burn
    r = compute_grit(100, 60, 0, 10, None)
    assert r["base"] == 80.0
    assert r["score"] == 80.0
    assert r["concentration_multiplier"] == 1.0 and r["inventory_multiplier"] == 1.0
    assert r["capped"] is False


def test_ten_points_in_either_half_moves_grit_by_five():
    assert score(100, 70, 0, 10, None) - score(100, 60, 0, 10, None) == pytest.approx(5)
    assert score(90, 60, 0, 10, None) - score(100, 60, 0, 10, None) == pytest.approx(-5)


# ---------- concentration multiplier ----------

@pytest.mark.parametrize(
    "hhi, expected",
    [
        (1499.9, 80.0),  # unconcentrated -> x1.0
        (1500, 72.0),    # moderate starts at 1,500 -> 80 x 0.9
        (2500, 72.0),    # 2,500 is still moderate -> x0.9
        (2500.1, 64.0),  # highly concentrated -> 80 x 0.8
    ],
)
def test_concentration_multiplier_hhi_boundaries(hhi, expected):
    assert score(100, 60, hhi, 10, None) == expected


# ---------- inventory multiplier ----------

@pytest.mark.parametrize(
    "days, expected",
    [
        (30, 80.0),    # not over 30 -> x1.0
        (30.1, 76.0),  # over 30 -> 80 x 0.95
        (60, 76.0),    # not over 60 -> x0.95
        (60.1, 68.0),  # over 60 -> 80 x 0.85
        (None, 68.0),  # no sales velocity -> worst bucket
    ],
)
def test_inventory_multiplier_boundaries(days, expected):
    assert score(100, 60, 0, days, None) == expected


def test_multipliers_compound():
    # 80 x 0.9 (HHI 2,000: moderate) x 0.95 (45 days) = 68.4
    assert score(100, 60, 2000, 45, None) == 68.4


# ---------- short-runway cap ----------

def test_cap_applies_under_three_months():
    r = compute_grit(100, 60, 0, 10, 2.99)
    assert r["score"] == SHORT_RUNWAY_CAP == 40
    assert r["capped"] is True


@pytest.mark.parametrize("runway", [3.0, 12.0, None])
def test_cap_does_not_apply_at_or_above_three_months(runway):
    r = compute_grit(100, 60, 0, 10, runway)
    assert r["score"] == 80.0
    assert r["capped"] is False


def test_cap_never_raises_a_low_score():
    r = compute_grit(20, 5, 0, 10, 1.0)
    assert r["score"] == 12.5  # 0.5 x 20 + 0.5 x 5
    assert r["capped"] is False


def test_score_bounded_0_to_100():
    assert score(0, 0, 100, None, 0.0) == 0
    assert score(100, 99.9, 0, 0, None) <= 100


# ---------- pipeline: the rule "no Grit > 40 under 3 months stressed runway" ----------

PROFITABLE = {
    "revenue": 1_000_000, "ad_spend": 300_000, "cogs": 400_000, "shipping_cost": 50_000,
    "rto_cost": 20_000, "fixed_costs": 200_000, "cash_in_bank": 500_000,
}


def analyse(**overrides):
    return process_business_state(FullBusinessState(**{**PROFITABLE, **overrides}))


# Concentration 0% and fast stock so the multipliers cannot hide a breach of the rule
CLEAN = {"top_platform_rev": 0, "top_supplier_spend": 0, "stock_units": 100, "daily_velocity": 100}


@pytest.mark.parametrize("behaviour", ["fixed", "scales"])
@pytest.mark.parametrize(
    "shocks",
    [
        {"cac_shock": 100},                      # runway 1.85
        {"rev_shock": 100},                      # runway 1.0 (fixed) / 2.5 (scales)
        {"cogs_shock": 50},                      # runway 2.94
        {"rev_shock": 50, "cac_shock": 20},      # runway 1.69 (fixed)
        {"fixed_costs": 600_000},                # audit loss-maker, runway 1.35, no shock
    ],
)
def test_no_grit_above_40_when_stressed_runway_under_3(behaviour, shocks):
    r = analyse(**CLEAN, **shocks, ad_spend_behaviour=behaviour)
    if r["simulation"]["runway"] is not None and r["simulation"]["runway"] < 3:
        assert r["grit_score"] <= 40


def test_no_shock_grit_equals_baseline_grit():
    r = analyse()
    assert r["grit_score"] == r["baseline_grit"]


def test_baseline_grit_includes_multipliers():
    # platform 800,000 / 1,000,000 = 80% top share -> HHI lower bound 80^2 = 6,400 (high) -> x0.8
    #   and the tier drops to Fragile (score 50: HHI > 2,500)
    # default stock 1,000 / 10 per day = 100 days -> x0.85
    # base = 0.5 x 50 + 0.5 x 99.9 = 74.95 -> 74.95 x 0.8 x 0.85 = 50.97 -> 51.0
    r = analyse(top_platform_rev=800_000)
    assert r["fragility"]["class"] == "Fragile"
    assert r["baseline_grit"] == 51.0
    assert r["grit_breakdown"]["concentration_multiplier"] == 0.8
    assert r["grit_breakdown"]["inventory_multiplier"] == 0.85


def test_cac_spike_grit_no_longer_generous():
    # Before Fix 2b: 46.0 at 1.85 months runway.
    # Now (80% top platform -> HHI 6,400): baseline tier Fragile (factor 0.8), stressed Critical (20)
    # estimate: λ = 1.85 x 0.8 = 1.48 -> exp(-6 / 1.48) = 1.7%
    # base = 0.5 x 20 + 0.5 x 1.7 = 10.85 -> x0.8 x0.85 = 7.38 -> 7.4
    r = analyse(cac_shock=100, top_platform_rev=800_000)
    assert r["grit_score"] == 7.4
