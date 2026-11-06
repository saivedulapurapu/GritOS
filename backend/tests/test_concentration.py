"""Fix 6: Herfindahl-Hirschman Index concentration (dependency_index.py) and where it feeds."""
import pytest
from fastapi.testclient import TestClient

import main
from dependency_index import get_dependency_score, hhi, hhi_band, validate_shares
from fragility_model import classify_fragility

api = TestClient(main.app)

BASE = {
    "revenue": 1_000_000, "ad_spend": 300_000, "cogs": 400_000, "shipping_cost": 50_000,
    "rto_cost": 20_000, "fixed_costs": 150_000, "cash_in_bank": 500_000,
}


@pytest.fixture(autouse=True)
def stub_advice(monkeypatch):
    monkeypatch.setattr(main.llm_advisor, "generate_strategic_advice", lambda metrics: ["stub"])


# ---------- HHI ----------

def test_single_source_is_10000():
    assert hhi([100]) == 10_000


def test_four_equal_sources_is_2500():
    # 4 x 25^2 = 4 x 625 = 2,500
    assert hhi([25, 25, 25, 25]) == 2_500


def test_mixed_shares():
    # 50^2 + 30^2 + 20^2 = 2,500 + 900 + 400 = 3,800
    assert hhi([50, 30, 20]) == 3_800


def test_partial_list_counts_only_listed_shares():
    # 40 % + 10 % listed, 50 % unlisted (treated as fragmented): 1,600 + 100 = 1,700
    assert hhi([40, 10]) == 1_700


@pytest.mark.parametrize(
    "value, band",
    [(0, "unconcentrated"), (1499.9, "unconcentrated"), (1500, "moderate"), (2500, "moderate"),
     (2500.1, "high"), (10_000, "high")],
)
def test_doj_ftc_bands(value, band):
    assert hhi_band(value) == band


@pytest.mark.parametrize("shares", [[101], [-1], [60, 50], [100, 0.1]])
def test_invalid_shares_rejected(shares):
    with pytest.raises(ValueError):
        validate_shares(shares)


def test_shares_summing_to_exactly_100_allowed():
    assert hhi([50, 50]) == 5_000


# ---------- dependency score: basis ----------

def test_share_list_basis_takes_precedence():
    d = get_dependency_score(800_000, 1_000_000, 0, 0, platform_shares=[30, 30, 40])
    assert d["platform_basis"] == "shares"
    assert d["platform_hhi"] == 3_400          # 900 + 900 + 1,600
    assert d["platform_dependency"] == 40.0    # largest listed share
    assert d["band"] == "high"


def test_top_share_only_is_a_lower_bound():
    # 800,000 of 1,000,000 = 80 % -> 80^2 = 6,400 (rest unknown, treated as fragmented)
    d = get_dependency_score(800_000, 1_000_000, 0, 0)
    assert (d["platform_basis"], d["platform_hhi"]) == ("top_share_only", 6_400)


def test_nothing_supplied_is_zero():
    d = get_dependency_score(0, 1_000_000, 0, 0)
    assert (d["platform_basis"], d["max_hhi"], d["band"]) == ("none", 0.0, "unconcentrated")


def test_max_hhi_is_larger_of_platform_and_supplier():
    d = get_dependency_score(0, 1_000_000, 0, 0, platform_shares=[20, 20], supplier_shares=[70])
    assert d["platform_hhi"] == 800 and d["supplier_hhi"] == 4_900 and d["max_hhi"] == 4_900


# ---------- fragility rules ----------

def test_high_concentration_makes_otherwise_resilient_business_fragile():
    r = classify_fragility(25.0, None, 0.2, concentration_hhi=2500.1)
    assert r["class"] == "Fragile"
    assert any("HHI" in reason for reason in r["reasons"])


def test_moderate_concentration_blocks_resilient():
    assert classify_fragility(25.0, None, 0.2, concentration_hhi=1500)["class"] == "Stable"
    assert classify_fragility(25.0, None, 0.2, concentration_hhi=1499.9)["class"] == "Resilient"


# ---------- API ----------

def test_analyze_with_share_lists():
    body = api.post("/api/analyze", json={**BASE, "platform_shares": [60, 25, 15],
                                         "supplier_shares": [50, 50]}).json()
    # platform: 3,600 + 625 + 225 = 4,450; supplier: 2,500 + 2,500 = 5,000
    assert body["dependency"]["platform_hhi"] == 4_450
    assert body["dependency"]["supplier_hhi"] == 5_000
    assert body["grit_breakdown"]["concentration_multiplier"] == 0.8
    assert body["fragility"]["class"] == "Fragile"


def test_shares_stored_with_scenario():
    sent = api.post("/api/analyze", json={**BASE, "platform_shares": [40, 30]}).json()
    detail = api.get(f"/api/scenarios/{sent['scenario_id']}").json()
    assert detail["extra_inputs"] == {"platform_shares": [40, 30]}


@pytest.mark.parametrize("shares", [[70, 40], [-5], [101], [1] * 51])
def test_invalid_share_lists_are_422(shares):
    assert api.post("/api/analyze", json={**BASE, "platform_shares": shares}).status_code == 422


def test_empty_share_list_means_not_supplied():
    body = api.post("/api/analyze", json={**BASE, "platform_shares": []}).json()
    assert body["dependency"]["platform_basis"] == "none"


def test_share_list_counts_for_completeness():
    with_shares = api.post("/api/analyze", json={**BASE, "platform_shares": [50, 50]}).json()
    without = api.post("/api/analyze", json=BASE).json()
    assert (with_shares["data_quality"]["dimensions"]["completeness"]["score"]
            > without["data_quality"]["dimensions"]["completeness"]["score"])
