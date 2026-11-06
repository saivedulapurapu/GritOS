"""process_business_state wiring — runway-decay estimate, sensitivity, fragility tiers, sentinel.

Calls the pipeline function directly (no server, no LLM: process_business_state
never calls Groq).
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


# ---------- Runway-decay estimate uses the SHOCKED runway (Fix 1) ----------

def test_estimate_falls_sharply_under_total_revenue_loss():
    # 100% revenue drop: vol 0 -> net = -200,000 (fixed costs only)
    # shocked runway = 500,000 / 200,000 = 2.5 months
    # λ = 2.5 x BASELINE factor (Resilient 1.0) = 2.5  ->  exp(-6 / 2.5) = exp(-2.4) = 9.07% -> 9.1
    # (if the stressed Critical factor 0.6 were used: λ = 1.5 -> 1.8%; it must not be)
    calm = analyse()
    shocked = analyse(rev_shock=100)
    assert calm["fragility"]["class"] == "Resilient"
    assert calm["runway_decay_estimate"] == 99.9
    assert shocked["simulation"]["runway"] == pytest.approx(2.5)
    assert shocked["runway_decay_estimate"] == 9.1


def test_estimate_is_computed_from_shocked_runway():
    # 50% revenue drop + 20% ad-cost spike: vol 0.5
    # rev 500,000 | ads 300,000*0.5*1.2 = 180,000 | COGS 200,000 | ship 25,000 | RTO 10,000
    # contribution 85,000; net = 85,000 - 200,000 = -115,000 -> runway 500,000/115,000 = 4.35
    r = analyse(rev_shock=50, kak_shock=20)
    assert r["simulation"]["runway"] == pytest.approx(4.35, abs=0.01)
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


# ---------- Fragility tiers: baseline vs stressed ----------

def test_baseline_tier_comes_from_baseline_not_shock():
    # The baseline tier describes structure; shocks act only through the shocked runway
    assert analyse()["fragility"]["class"] == analyse(rev_shock=100)["fragility"]["class"]


def test_revenue_wipeout_baseline_resilient_stressed_critical():
    # Shocked: revenue 0 -> margin 0% (guarded) -> "0% or negative"; runway 2.5 -> "under 3 months"
    r = analyse(rev_shock=100)
    assert r["fragility"]["class"] == "Resilient"
    assert r["fragility"]["stressed_class"] == "Critical"
    assert "Runway under 3 months" in r["fragility"]["stressed_reasons"]
    assert any("margin" in reason for reason in r["fragility"]["stressed_reasons"])


def test_ad_cost_spike_stressed_critical():
    # CAC +100%: ads 600,000 -> contribution -70,000 -> margin -7%; runway 500,000/270,000 = 1.85
    r = analyse(kak_shock=100)
    assert r["fragility"]["class"] == "Resilient"
    assert r["fragility"]["stressed_class"] == "Critical"


def test_mild_shock_keeps_resilient():
    # Revenue -20%: vol 0.8 -> rev 800,000, variable costs scale -> contribution 184,000 (23%)
    # net = 184,000 - 200,000 = -16,000 -> runway 500,000/16,000 = 31.25 months (>= 12), ad ratio 0.3
    r = analyse(rev_shock=20)
    assert r["simulation"]["runway"] == pytest.approx(31.25)
    assert r["fragility"]["stressed_class"] == "Resilient"


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


# ---------- Sensitivity covers all shocks and is returned (Fix 1) ----------

def test_sensitivity_is_returned_in_fragility():
    r = analyse()
    assert "sensitivity" in r["fragility"]
    assert r["fragility"]["sensitivity"] == 0  # no shock


@pytest.mark.parametrize(
    "shock, expected_runway",
    [
        # ads 450,000 -> contribution 80,000 -> net -120,000 -> 500,000/120,000 = 4.17
        ("kak_shock", 4.17),
        # vol 0.5 -> contribution 115,000 -> net -85,000 -> 500,000/85,000 = 5.88
        ("rev_shock", 5.88),
        # COGS 600,000 -> contribution 30,000 -> net -170,000 -> 500,000/170,000 = 2.94
        ("cogs_shock", 2.94),
    ],
)
def test_every_shock_type_moves_sensitivity(shock, expected_runway):
    # Previously only rev_shock counted, so ad-cost and COGS shocks gave sensitivity 0
    r = analyse(**{shock: 50})
    assert r["simulation"]["runway"] == pytest.approx(expected_runway, abs=0.01)
    # (12 - runway) / 50
    assert r["fragility"]["sensitivity"] == pytest.approx((12 - expected_runway) / 50, abs=0.001)
    assert r["fragility"]["sensitivity"] > 0


def test_sensitivity_uses_sum_of_all_shocks():
    r = analyse(kak_shock=20, rev_shock=30, cogs_shock=10)
    assert r["fragility"]["sensitivity"] == get_shock_sensitivity(None, r["simulation"]["runway"], 60)


# ---------- Runway / days sentinel is None end-to-end (Fix 1) ----------

def test_profitable_runways_are_none():
    r = analyse()
    assert r["baseline"]["runway_months"] is None
    assert r["simulation"]["runway"] is None


def test_zero_sales_velocity_does_not_crash_pipeline():
    # days_to_liquidate None -> treated as worst inventory bucket (penalty 0.85)
    r = analyse(daily_velocity=0)
    assert r["inventory"]["days_to_liquidate"] is None
    assert r["inventory"]["risk_level"] == "RED"
    assert r["grit_score"] >= 0
