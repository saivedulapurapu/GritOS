"""Fix 1: process_business_state wiring — survival, sensitivity, runway sentinel.

Calls the pipeline function directly (no server, no LLM: process_business_state
never calls Groq). Assertions are written so they stay valid when the fragility
classifier is replaced in Fix 2.
"""
import pytest

import survival
from fragility_model import get_shock_sensitivity
from main import FullBusinessState, process_business_state

# Unshocked: contribution = 1,000,000 - 300,000 - 400,000 - 50,000 - 20,000 = 230,000
#            net = 230,000 - 200,000 = +30,000 -> profitable -> runway None
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


# ---------- Bug 1: survival must use the SHOCKED runway ----------

def test_survival_falls_sharply_under_total_revenue_loss():
    # 100% revenue drop: vol 0 -> net = -200,000 (fixed costs only)
    # shocked runway = 500,000 / 200,000 = 2.5 months
    # sensitivity = (12 - 2.5) / 100 = 0.095
    # survival = exp(-6 / λ) with λ = 2.5 × class factor (max 2.5) − 0.0095 ≤ 6.24
    #          ≤ exp(-6 / 6.24) ≈ 38%, whatever the fragility class
    calm = analyse()
    shocked = analyse(rev_shock=100)
    assert calm["survival_prob"] > 98
    assert shocked["simulation"]["runway"] == pytest.approx(2.5)
    assert shocked["survival_prob"] < 40


def test_survival_is_computed_from_shocked_runway():
    # 50% revenue drop + 20% ad-cost spike: vol 0.5
    # rev 500,000 | ads 300,000*0.5*1.2 = 180,000 | COGS 200,000 | ship 25,000 | RTO 10,000
    # contribution 85,000; net = 85,000 - 200,000 = -115,000 -> runway 500,000/115,000 = 4.35
    r = analyse(rev_shock=50, kak_shock=20)
    assert r["simulation"]["runway"] == pytest.approx(4.35, abs=0.01)
    expected = survival.calculate_survival_probability(
        r["simulation"]["runway"], r["fragility"]["class"], r["fragility"]["sensitivity"]
    )
    assert r["survival_prob"] == expected


def test_trajectory_uses_shocked_runway():
    # Month 6 of the trajectory is the same formula as the 6-month survival probability
    r = analyse(rev_shock=100)
    assert r["trajectory"][-1]["prob"] == r["survival_prob"]


def test_baseline_survival_ignores_shocks():
    assert analyse()["baseline_survival_prob"] == analyse(rev_shock=100)["baseline_survival_prob"]


def test_no_shock_scenario_equals_baseline():
    r = analyse()
    assert r["survival_prob"] == r["baseline_survival_prob"]


# ---------- Bug 2: sensitivity covers all shocks and is returned ----------

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


# ---------- Bug 5: runway / days sentinel is None end-to-end ----------

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
