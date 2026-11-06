"""Fix 3: soft data-quality report (data_quality.py)."""
import pytest
from fastapi.testclient import TestClient

import data_quality
import main
from data_quality import OPTIONAL_INPUTS, QualityReport, WEIGHTS
from main import FullBusinessState, process_business_state

FULL = {
    "revenue": 1_000_000, "ad_spend": 300_000, "cogs": 400_000, "shipping_cost": 50_000,
    "rto_cost": 20_000, "fixed_costs": 150_000, "cash_in_bank": 500_000,
    "stock_units": 1_000, "cost_per_unit": 100, "daily_velocity": 50,
    "top_platform_rev": 300_000, "top_supplier_spend": 100_000, "total_purchases": 400_000,
}


def report_for(**overrides):
    state = FullBusinessState(**{**FULL, **overrides})
    return data_quality.build_report(state, process_business_state(state))


def codes(r):
    return {i["code"] for i in r["issues"]}


# ---------- clean input ----------

def test_clean_complete_input_scores_100():
    r = report_for()
    assert r["score"] == 100.0
    assert r["issues"] == []
    assert set(r["dimensions"]) == {"completeness", "validity", "consistency", "plausibility"}


# ---------- completeness ----------

def test_completeness_is_share_of_optional_inputs_supplied():
    required = {k: FULL[k] for k in ("revenue", "ad_spend", "cogs", "shipping_cost", "fixed_costs", "cash_in_bank")}
    state = FullBusinessState(**required)
    r = data_quality.build_report(state, process_business_state(state))
    # 0 of 7 optional inputs supplied -> completeness 0, one info issue per default
    assert r["dimensions"]["completeness"]["score"] == 0
    assert sum(1 for i in r["issues"] if i["code"] == "default_used") == len(OPTIONAL_INPUTS) == 7


def test_partial_completeness():
    state = FullBusinessState(**{k: v for k, v in FULL.items() if k not in ("top_platform_rev", "total_purchases", "top_supplier_spend")})
    r = data_quality.build_report(state, process_business_state(state))
    # 4 of 7 supplied -> 57.1
    assert r["dimensions"]["completeness"]["score"] == pytest.approx(57.1, abs=0.05)


# ---------- validity / consistency / plausibility ----------

def test_zero_revenue_is_a_soft_validity_warning():
    r = report_for(revenue=0, top_platform_rev=0)
    assert "zero_revenue" in codes(r)
    assert r["dimensions"]["validity"]["score"] == 80  # one warning = -20


def test_costs_above_revenue_flagged_as_consistency():
    r = report_for(ad_spend=1_200_000, cogs=1_100_000)
    assert {"ad_spend_exceeds_revenue", "cogs_exceeds_revenue"} <= codes(r)
    assert r["dimensions"]["consistency"]["score"] == 60  # two warnings


def test_logistics_above_revenue_flagged():
    assert "logistics_exceed_revenue" in codes(report_for(shipping_cost=900_000, rto_cost=200_000))


def test_margin_above_90_percent_implausible():
    # contribution = 1,000,000 - 10,000 - 10,000 - 0 - 0 = 980,000 -> 98%
    r = report_for(ad_spend=10_000, cogs=10_000, shipping_cost=0, rto_cost=0)
    assert "margin_too_high" in codes(r)


def test_runway_above_120_months_implausible():
    # contribution 230,000 - fixed 231,000 = -1,000/month burn; cash 500,000 -> 500 months
    r = report_for(fixed_costs=231_000)
    assert "runway_too_long" in codes(r)


def test_more_than_a_year_of_stock_implausible():
    # 40,000 units / 100 per day = 400 days
    assert "stock_days_too_high" in codes(report_for(stock_units=40_000, daily_velocity=100))


def test_zero_unit_cost_with_stock_flagged():
    assert "zero_unit_cost" in codes(report_for(cost_per_unit=0))


# ---------- scoring rules ----------

def test_penalty_scoring_and_weighted_overall():
    rep = QualityReport()
    rep.add("validity", "a", "warning", "x")        # validity 80
    rep.add("consistency", "b", "error", "x")       # consistency 60
    rep.add("consistency", "c", "info", "x")        # consistency 55
    rep.touch("plausibility")                        # plausibility 100
    rep.set_score("completeness", 50)                # completeness 50
    d = rep.to_dict()
    # (80 x .30 + 55 x .25 + 100 x .25 + 50 x .20) / 1.0 = 24 + 13.75 + 25 + 10 = 72.75
    assert d["score"] == pytest.approx(72.8, abs=0.05)


def test_dimension_score_floors_at_zero():
    rep = QualityReport()
    for i in range(4):
        rep.add("validity", f"e{i}", "error", "x")
    assert rep.to_dict()["dimensions"]["validity"]["score"] == 0


def test_extra_dimensions_are_weighted_in_for_the_edgar_path():
    # Extension point used by the SEC EDGAR path
    rep = QualityReport()
    rep.touch("validity")                  # 100, weight .30
    rep.set_score("provenance", 50)        # weight .30
    # (100 x .30 + 50 x .30) / .60 = 75
    assert rep.to_dict()["score"] == 75.0
    assert WEIGHTS["provenance"] == 0.30 and WEIGHTS["source"] == 0.20


def test_unknown_severity_rejected():
    with pytest.raises(ValueError):
        QualityReport().add("validity", "x", "fatal", "x")


# ---------- API ----------

def test_analyze_returns_data_quality(monkeypatch):
    monkeypatch.setattr(main.llm_advisor, "generate_strategic_advice", lambda metrics: ["stub"])
    r = TestClient(main.app).post("/api/analyze", json={**FULL, "ad_spend": 1_500_000})
    assert r.status_code == 200
    dq = r.json()["data_quality"]
    assert 0 <= dq["score"] <= 100
    assert "ad_spend_exceeds_revenue" in {i["code"] for i in dq["issues"]}
