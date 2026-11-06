"""Fix 5: company-quarter -> GritOS inputs with provenance; EDGAR data-quality dimensions; validation maths."""
from datetime import date

import pytest

import data_quality
from etl.edgar_to_gritos import map_quarter, provenance_mix, source_checks
from etl.validation import _row_metrics, summarize
from pipeline import process_business_state
from schemas import FullBusinessState


def quarter(**overrides):
    # Q1 2024 (91 days). Quarterly: revenue 300, COGS 120, operating income 30, FY advertising 240,
    # marketing 45, cash 1000, inventory 400 (all in $; small numbers keep the hand maths readable)
    q = {
        "quarter": "2024-Q1", "period_start": date(2024, 1, 1), "period_end": date(2024, 3, 31),
        "revenue": 300.0, "cogs": 120.0, "operating_income": 30.0, "advertising_annual": 240.0,
        "marketing": 45.0, "general_admin": None, "research_dev": None, "sga": None,
        "cash": 1000.0, "inventory": 400.0, "operating_cash_flow": 21.0, "share_based_comp": 6.0,
        "depreciation_amortization": 3.0,
        "provenance": {"revenue": "REAL", "cogs": "REAL", "operating_income": "REAL", "marketing": "REAL",
                       "cash": "REAL", "inventory": "REAL", "operating_cash_flow": "REAL"},
        "detail": {"revenue": {"tag": "RevenueFromContractWithCustomerExcludingAssessedTax", "method": "reported"},
                   "cogs": {"tag": "CostOfGoodsAndServicesSold", "method": "reported"},
                   "operating_income": {"tag": "OperatingIncomeLoss", "method": "reported"},
                   "cash": {"tag": "CashAndCashEquivalentsAtCarryingValue", "method": "reported"}},
    }
    q.update(overrides)
    return q


def test_full_mapping_hand_calculated():
    m = map_quarter(quarter(), "Test Co")
    i = m["inputs"]
    assert m["analysable"] and m["missing"] == [] and m["adjustments"] == []
    assert i["revenue"] == 100                    # 300 / 3
    assert i["cogs"] == 40                        # 120 / 3
    assert i["ad_spend"] == 20                    # FY advertising 240 / 12
    # operating expenses = 300 - 120 - 30 = 150 per quarter -> 50 / month; fixed = 50 - 20 = 30
    assert i["fixed_costs"] == pytest.approx(30)
    assert i["shipping_cost"] == 0 and i["rto_cost"] == 0
    assert i["cash_in_bank"] == 1000 and i["currency"] == "USD" and i["business_name"] == "Test Co"
    # inventory in $1 units; velocity = 120 / 91 days
    assert (i["stock_units"], i["cost_per_unit"]) == (400, 1.0)
    assert i["daily_velocity"] == pytest.approx(120 / 91)


def test_gritos_net_equals_reported_operating_income_over_three():
    # 100 - 20 - 40 - 0 - 0 - 30 = 10 = operating income 30 / 3
    m = map_quarter(quarter(), "Test Co")
    analysis = process_business_state(FullBusinessState(**m["inputs"]))
    assert analysis["baseline"]["net_profit"] == pytest.approx(10)
    # days to sell through = 400 / (120 / 91) = 303.3
    assert analysis["inventory"]["days_to_liquidate"] == pytest.approx(303.3, abs=0.05)


def test_provenance_statuses():
    p = map_quarter(quarter(), "Test Co")["provenance"]
    assert {f: p[f]["status"] for f in p} == {
        "revenue": "REAL", "cogs": "REAL", "ad_spend": "DERIVED", "fixed_costs": "DERIVED",
        "shipping_cost": "ASSUMED", "rto_cost": "ASSUMED", "cash_in_bank": "REAL", "stock_units": "REAL",
        "cost_per_unit": "ASSUMED", "daily_velocity": "DERIVED", "concentration": "ASSUMED",
    }
    assert "stock comp" in p["fixed_costs"]["note"]


def test_provenance_mix_percentages():
    # 11 fields: REAL 4, DERIVED 3, ASSUMED 4
    assert map_quarter(quarter(), "Test Co")["provenance_mix"] == {"REAL": 36.4, "DERIVED": 27.3, "ASSUMED": 36.4}
    assert provenance_mix({}) == {}


def test_marketing_used_as_labelled_proxy_without_annual_advertising():
    m = map_quarter(quarter(advertising_annual=None), "Test Co")
    assert m["inputs"]["ad_spend"] == 15                      # 45 / 3
    assert m["inputs"]["fixed_costs"] == pytest.approx(35)    # 50 - 15
    assert m["provenance"]["ad_spend"]["status"] == "PROXY"
    assert "overstates" in m["provenance"]["ad_spend"]["note"]


def test_no_ad_figure_assumes_zero_and_keeps_opex_in_fixed():
    m = map_quarter(quarter(advertising_annual=None, marketing=None), "Test Co")
    assert m["inputs"]["ad_spend"] == 0 and m["inputs"]["fixed_costs"] == pytest.approx(50)
    assert m["provenance"]["ad_spend"]["status"] == "ASSUMED"


def test_ad_spend_capped_at_operating_expenses():
    # FY advertising 1200 -> 100 / month > opex 50 / month -> capped at 50, fixed 0
    m = map_quarter(quarter(advertising_annual=1200.0), "Test Co")
    assert m["inputs"]["ad_spend"] == pytest.approx(50) and m["inputs"]["fixed_costs"] == 0
    assert len(m["adjustments"]) == 1


def test_negative_operating_expenses_floored_at_zero():
    # operating income 200 > gross profit 180 (e.g. a gain) -> opex -20 / quarter
    m = map_quarter(quarter(operating_income=200.0), "Test Co")
    assert m["inputs"]["ad_spend"] == 0 and m["inputs"]["fixed_costs"] == 0
    assert len(m["adjustments"]) == 2


@pytest.mark.parametrize("missing", ["revenue", "cogs", "operating_income", "cash"])
def test_missing_required_concept_makes_quarter_not_analysable(missing):
    m = map_quarter(quarter(**{missing: None}), "Test Co")
    assert not m["analysable"] and m["inputs"] is None
    expected = {"revenue": "revenue", "cogs": "cogs", "operating_income": "fixed_costs", "cash": "cash_in_bank"}
    assert expected[missing] in m["missing"]


def test_missing_inventory_is_assumed_none():
    m = map_quarter(quarter(inventory=None), "Test Co")
    assert m["inputs"]["stock_units"] == 0 and m["inputs"]["daily_velocity"] == 0
    assert m["provenance"]["stock_units"]["status"] == "ASSUMED"


def test_derived_quarter_noted():
    q = quarter()
    q["detail"]["revenue"]["method"] = "q4_from_fy"
    q["provenance"]["revenue"] = "DERIVED"
    p = map_quarter(q, "Test Co")["provenance"]["revenue"]
    assert p["status"] == "DERIVED" and "FY - (Q1 + Q2 + Q3)" in p["note"]


def test_source_checks():
    q = quarter(operating_cash_flow=None)
    q["detail"]["cash"]["tag"] = "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
    q["detail"]["revenue"]["method"] = "ytd_difference"
    s = source_checks(q, restatements=[])
    assert s["derived_concepts"] == ["revenue"]
    assert s["non_primary_tags"] == {"cash": "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"}
    assert s["missing_validation_concepts"] == ["operating_cash_flow"]


# ---------- EDGAR data-quality dimensions ----------

def test_edgar_quality_dimensions_hand_calculated():
    m = map_quarter(quarter(), "Test Co")
    state = FullBusinessState(**m["inputs"])
    report = data_quality.assess_manual_inputs(state, process_business_state(state))
    restatement = {"kind": "restatement", "concept": "revenue", "period_end": "2024-03-31",
                   "original_value": 310.0, "restated_value": 300.0}
    data_quality.assess_edgar(report, m, source_checks(quarter(), [restatement]))
    d = report.to_dict()["dimensions"]
    # provenance = (4 x 1.0 + 3 x 0.8 + 4 x 0.3) / 11 x 100 = 69.1
    assert d["provenance"]["score"] == pytest.approx(69.1, abs=0.05)
    # source: one restatement (info, -5)
    assert d["source"]["score"] == 95
    codes = {i["code"] for i in report.to_dict()["issues"]}
    assert {"assumed", "restated_restatement"} <= codes


def test_missing_and_adjustment_are_warnings():
    m = map_quarter(quarter(advertising_annual=1200.0), "Test Co")
    m["provenance"]["cash_in_bank"]["status"] = "MISSING"
    report = data_quality.QualityReport()
    data_quality.assess_edgar(report, m, {"restatements": [], "derived_concepts": [], "non_primary_tags": {},
                                          "missing_validation_concepts": []})
    sev = {(i["dimension"], i["code"]): i["severity"] for i in report.issues}
    assert sev[("provenance", "missing")] == "warning"
    assert sev[("source", "mapping_adjustment")] == "warning"


# ---------- validation metrics ----------

class R:
    def __init__(self, net, ocf, rev, addback):
        self.gritos_monthly_net, self.ocf_monthly, self.revenue_monthly, self.noncash_addback_monthly = net, ocf, rev, addback


def test_row_metrics_hand_calculated():
    # GritOS net -10, OCF +5, revenue 100: error -15 (more pessimistic), 15 % of revenue, signs disagree
    # add-back (SBC + D&A) 12 -> error after add-back -3
    m = _row_metrics(R(-10, 5, 100, 12))
    assert m["error"] == -15 and m["abs_error_pct_revenue"] == 15
    assert m["sign_agrees"] is False and m["error_after_addback"] == -3


def test_summarize_hand_calculated():
    rows = [{"ticker": "A", **_row_metrics(R(-10, 5, 100, 12))},     # err -15 (15 %), after add-back -3 (3 %)
            {"ticker": "A", **_row_metrics(R(20, 15, 200, None))},   # err +5 (2.5 %), no add-back
            {"ticker": "B", **_row_metrics(R(-30, -20, 100, 5))}]    # err -10 (10 %), after add-back -5 (5 %)
    s = summarize(rows)
    o = s["overall"]
    assert o["quarters"] == 3
    assert o["mae_usd_monthly"] == 10                          # (15 + 5 + 10) / 3
    assert o["median_abs_error_pct_revenue"] == 10.0           # median of 15, 2.5, 10
    assert o["mean_abs_error_pct_revenue"] == 9.2              # 27.5 / 3
    assert o["gritos_more_pessimistic_pct"] == 66.7            # 2 of 3 errors negative
    assert o["sign_agreement_pct"] == 66.7                     # rows 2 and 3
    assert o["median_abs_error_pct_revenue_after_addback"] == 4.0   # median of 3, 5
    assert s["by_company"]["A"]["quarters"] == 2
    assert summarize([])["overall"] == {"quarters": 0}
