"""process_business_state wiring — runway-decay estimate, sensitivity, fragility tiers, sentinel.

Calls the pipeline function directly (no server, no LLM: process_business_state
never calls Groq). Default ad_spend_behaviour is "fixed" (Fix 2b); tests that
need the opt-in "scales" mode say so.
"""
import pytest

import runway_decay
from fragility_model import get_shock_sensitivity
from main import FullBusinessState, process_business_state

# Unshocked: contribution = 1,000,000 - 300,000 - 400,000 - 50,000 - 20,000 = 230,000
#            net = 230,000 - 200,000 = +30,000 -> profitable -> runway None
#            margin 23%, ad ratio 0.3 -> baseline tier Resilient
PROFITABLE = {
    "revenue": 1_000_000,
    "ad_spend": 300_000,
    "cogs": 400_000,
    "shipping_cost": 50_000,
    "rto_cost": 20_000,
    "fixed_costs": 200_000,
    "cash_in_bank": 500_000,
}


def analyse(**overrides):
    return process_business_state(FullBusinessState(**{**PROFITABLE, **overrides}))


# ---------- Runway-decay estimate uses the SHOCKED runway ----------

def test_estimate_falls_sharply_under_total_revenue_loss():
    # Default "fixed" ads: revenue 0, ads still 300,000 -> contribution -300,000
    # net = -300,000 - 200,000 = -500,000 -> runway = 500,000 / 500,000 = 1.0 month
    # λ = 1.0 x BASELINE factor (Resilient 1.0) = 1.0 -> exp(-6) = 0.25% -> 0.2
    calm = analyse()
    shocked = analyse(rev_shock=100)
    assert calm["fragility"]["class"] == "Resilient"
    assert calm["runway_decay_estimate"] == 99.9
    assert shocked["simulation"]["runway"] == pytest.approx(1.0)
    assert shocked["runway_decay_estimate"] == 0.2


def test_total_revenue_loss_when_ads_scale():
    # "scales": vol 0 -> all variable costs 0 -> net = -200,000 -> runway 2.5
    # λ = 2.5 x BASELINE factor 1.0 -> exp(-6 / 2.5) = 9.07% -> 9.1
    # (if the stressed Critical factor 0.6 were used: λ = 1.5 -> 1.8%; it must not be)
    r = analyse(rev_shock=100, ad_spend_behaviour="scales")
    assert r["simulation"]["runway"] == pytest.approx(2.5)
    assert r["runway_decay_estimate"] == 9.1


def test_estimate_is_computed_from_shocked_runway():
    # 50% revenue drop + 20% ad-cost spike, "fixed" ads: vol 0.5
    # rev 500,000 | ads 300,000 x 1.2 = 360,000 | COGS 200,000 | ship 25,000 | RTO 10,000
    # contribution -95,000; net = -95,000 - 200,000 = -295,000 -> runway 500,000/295,000 = 1.69
    r = analyse(rev_shock=50, cac_shock=20)
    assert r["simulation"]["runway"] == pytest.approx(1.69, abs=0.01)
    expected = runway_decay.calculate_runway_decay_estimate(r["simulation"]["runway"], r["fragility"]["class"])
    assert r["runway_decay_estimate"] == expected


def test_trajectory_uses_shocked_runway():
    # Month 6 of the trajectory is the same formula as the 6-month estimate
    r = analyse(rev_shock=100)
    assert r["trajectory"][-1]["prob"] == r["runway_decay_estimate"]


def test_baseline_estimate_ignores_shocks():
    assert (analyse()["baseline_runway_decay_estimate"]
            == analyse(rev_shock=100)["baseline_runway_decay_estimate"])


def test_no_shock_scenario_equals_baseline():
    r = analyse()
    assert r["runway_decay_estimate"] == r["baseline_runway_decay_estimate"]


def test_old_survival_field_names_are_gone():
    r = analyse()
    assert "survival_prob" not in r and "baseline_survival_prob" not in r


# ---------- ad_spend_behaviour reaches the shock engine ----------

def test_ad_spend_behaviour_defaults_to_fixed():
    assert FullBusinessState(**PROFITABLE).ad_spend_behaviour == "fixed"


def test_fixed_ads_shorten_runway_vs_scaling_ads():
    # Revenue -50%: fixed -> net -235,000 -> runway 2.13 | scales -> net -85,000 -> runway 5.88
    fixed = analyse(rev_shock=50)
    scales = analyse(rev_shock=50, ad_spend_behaviour="scales")
    assert fixed["simulation"]["runway"] == pytest.approx(2.13)
    assert scales["simulation"]["runway"] == pytest.approx(5.88)


def test_invalid_ad_spend_behaviour_rejected_by_schema():
    with pytest.raises(ValueError):
        FullBusinessState(**PROFITABLE, ad_spend_behaviour="sometimes")


# ---------- Fragility tiers: baseline vs stressed ----------

def test_baseline_tier_comes_from_baseline_not_shock():
    # The baseline tier describes structure; shocks act only through the shocked runway
    assert analyse()["fragility"]["class"] == analyse(rev_shock=100)["fragility"]["class"]


@pytest.mark.parametrize("behaviour", ["fixed", "scales"])
def test_revenue_wipeout_baseline_resilient_stressed_critical(behaviour):
    # Shocked: revenue 0 -> margin 0% (guarded) -> "0% or negative"; runway 1.0 (fixed) / 2.5 (scales)
    r = analyse(rev_shock=100, ad_spend_behaviour=behaviour)
    assert r["fragility"]["class"] == "Resilient"
    assert r["fragility"]["stressed_class"] == "Critical"
    assert "Runway under 3 months" in r["fragility"]["stressed_reasons"]
    assert any("margin" in reason for reason in r["fragility"]["stressed_reasons"])


def test_ad_cost_spike_stressed_critical():
    # CAC +100%: ads 600,000 -> contribution -70,000 -> margin -7%; runway 500,000/270,000 = 1.85
    r = analyse(cac_shock=100)
    assert r["fragility"]["class"] == "Resilient"
    assert r["fragility"]["stressed_class"] == "Critical"


def test_mild_shock_tier_depends_on_ad_behaviour():
    # Revenue -20%, vol 0.8: rev 800,000 | COGS 320,000 | ship 40,000 | RTO 16,000
    # scales: ads 240,000 -> contribution 184,000 (23%) -> net -16,000 -> runway 31.25, ad 0.3 -> Resilient
    # fixed:  ads 300,000 -> contribution 124,000 (15.5%) -> net -76,000 -> runway 6.58, ad 0.375 -> Stable
    scales = analyse(rev_shock=20, ad_spend_behaviour="scales")
    fixed = analyse(rev_shock=20)
    assert scales["simulation"]["runway"] == pytest.approx(31.25)
    assert scales["fragility"]["stressed_class"] == "Resilient"
    assert fixed["simulation"]["runway"] == pytest.approx(6.58)
    assert fixed["fragility"]["stressed_class"] == "Stable"


def test_no_shock_stressed_equals_baseline():
    r = analyse()
    assert r["fragility"]["stressed_class"] == r["fragility"]["class"]
    assert r["fragility"]["stressed_reasons"] == r["fragility"]["reasons"]


def test_loss_maker_from_audit_is_critical():
    # Audit case: fixed 600,000 -> net = 230,000 - 600,000 = -370,000
    # runway = 500,000 / 370,000 = 1.35 months -> under 3 -> Critical
    # (the old RandomForest called this "Anti-Fragile")
    r = analyse(fixed_costs=600_000)
    assert r["baseline"]["runway_months"] == pytest.approx(1.35)
    assert r["fragility"]["class"] == "Critical"
    # λ = 1.35 x 0.6 = 0.81  ->  exp(-6 / 0.81) = exp(-7.41) = 0.06% -> 0.1
    assert r["runway_decay_estimate"] == 0.1


# ---------- Sensitivity and months lost ----------

def test_sensitivity_is_returned_in_fragility():
    r = analyse()
    assert "sensitivity" in r["fragility"]
    assert r["fragility"]["sensitivity"] == 0  # no shock


@pytest.mark.parametrize(
    "shock, expected_runway",
    [
        # ads 450,000 -> contribution 80,000 -> net -120,000 -> 500,000/120,000 = 4.17
        ("cac_shock", 4.17),
        # fixed ads: rev 500,000 - ads 300,000 - COGS 200,000 - 35,000 = -35,000
        #   -> net -235,000 -> 500,000/235,000 = 2.13
        ("rev_shock", 2.13),
        # COGS 600,000 -> contribution 30,000 -> net -170,000 -> 500,000/170,000 = 2.94
        ("cogs_shock", 2.94),
    ],
)
def test_every_shock_type_moves_sensitivity(shock, expected_runway):
    r = analyse(**{shock: 50})
    assert r["simulation"]["runway"] == pytest.approx(expected_runway, abs=0.01)
    # (12 - runway) / 50
    assert r["fragility"]["sensitivity"] == pytest.approx((12 - expected_runway) / 50, abs=0.001)
    assert r["fragility"]["sensitivity"] > 0


def test_sensitivity_uses_sum_of_all_shocks():
    r = analyse(cac_shock=20, rev_shock=30, cogs_shock=10)
    assert r["fragility"]["sensitivity"] == get_shock_sensitivity(None, r["simulation"]["runway"], 60)


def test_months_lost_uses_12_month_horizon():
    # Baseline no burn -> counts as 12; shocked runway 1.0 -> 12 - 1.0 = 11.0 months lost
    r = analyse(rev_shock=100)
    assert r["simulation"]["runway_lost_months"] == pytest.approx(11.0)
    # Consistent with sensitivity: 11.0 / 100 = 0.11
    assert r["fragility"]["sensitivity"] == pytest.approx(0.11)


def test_months_lost_zero_when_runway_stays_beyond_horizon():
    # scales, revenue -20%: runway 31.25 -> both capped at 12 -> 0 lost
    r = analyse(rev_shock=20, ad_spend_behaviour="scales")
    assert r["simulation"]["runway_lost_months"] == 0


# ---------- Runway / days sentinel is None end-to-end ----------

def test_profitable_runways_are_none():
    r = analyse()
    assert r["baseline"]["runway_months"] is None
    assert r["simulation"]["runway"] is None


def test_zero_sales_velocity_does_not_crash_pipeline():
    # No stock and no sales: nothing locked -> 0 days, GREEN, no inventory haircut.
    # (Stock > 0 with zero velocity is now rejected by the schema: see test_schemas.py.)
    r = analyse(stock_units=0, daily_velocity=0)
    assert r["inventory"]["days_to_liquidate"] == 0
    assert r["inventory"]["risk_level"] == "GREEN"
    assert r["grit_breakdown"]["inventory_multiplier"] == 1.0
