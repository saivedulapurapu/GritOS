"""Fix 4: every /api/analyze is saved; history and scenario detail endpoints (temp DB per test)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

import db
import main

api = TestClient(main.app)

BASE = {
    "revenue": 1_000_000, "ad_spend": 300_000, "cogs": 400_000, "shipping_cost": 50_000,
    "rto_cost": 20_000, "fixed_costs": 150_000, "cash_in_bank": 500_000,
}


@pytest.fixture(autouse=True)
def stub_advice(monkeypatch):
    monkeypatch.setattr(main.llm_advisor, "generate_strategic_advice", lambda metrics: ["stub"])


def analyse(**overrides):
    r = api.post("/api/analyze", json={**BASE, **overrides})
    assert r.status_code == 200, r.text
    return r.json()


def count(Session, model):
    with Session() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_schema_tables_and_foreign_keys(temp_db):
    insp = inspect(temp_db.kw["bind"])
    assert {"businesses", "scenarios", "results", "quality_issues"} <= set(insp.get_table_names())
    fk_targets = {fk["referred_table"] for t in ("scenarios", "results", "quality_issues") for fk in insp.get_foreign_keys(t)}
    assert fk_targets == {"businesses", "scenarios", "results"}
    assert any(ix["column_names"] == ["created_at"] for ix in insp.get_indexes("scenarios"))


def test_analyze_saves_scenario_result_and_issues(temp_db):
    body = analyse(ad_spend=1_200_000)  # triggers an ad_spend_exceeds_revenue issue
    assert isinstance(body["scenario_id"], int)
    assert count(temp_db, db.Scenario) == 1
    assert count(temp_db, db.Result) == 1
    with temp_db() as s:
        codes = set(s.scalars(select(db.QualityIssue.code)))
    assert "ad_spend_exceeds_revenue" in codes


def test_failed_validation_saves_nothing(temp_db):
    assert api.post("/api/analyze", json={**BASE, "revenue": -1}).status_code == 422
    assert count(temp_db, db.Scenario) == 0


def test_same_business_name_reuses_business_row(temp_db):
    analyse(business_name="Acme")
    analyse(business_name="Acme", rev_shock=50)
    analyse(business_name="Other")
    assert count(temp_db, db.Business) == 2
    assert count(temp_db, db.Scenario) == 3


def test_history_newest_first_and_filters(temp_db):
    first = analyse(business_name="Acme")["scenario_id"]
    second = analyse(business_name="Acme", rev_shock=100)["scenario_id"]
    analyse(business_name="Other")
    rows = api.get("/api/history").json()
    assert [r["scenario_id"] for r in rows][:2] == [rows[0]["scenario_id"], rows[1]["scenario_id"]]
    assert rows[0]["business"] == "Other"
    acme = api.get("/api/history", params={"business": "Acme"}).json()
    assert [r["scenario_id"] for r in acme] == [second, first]
    assert acme[0]["shocks"]["rev_shock"] == 100
    assert acme[0]["stressed_tier"] == "Critical"


def test_history_limit_validated(temp_db):
    for _ in range(3):
        analyse()
    assert len(api.get("/api/history", params={"limit": 2}).json()) == 2
    assert api.get("/api/history", params={"limit": 0}).status_code == 422
    assert api.get("/api/history", params={"limit": 501}).status_code == 422


def test_scenario_detail_round_trips_inputs_and_result(temp_db):
    sent = analyse(cac_shock=40, currency="USD", business_name="Round trip")
    detail = api.get(f"/api/scenarios/{sent['scenario_id']}").json()
    assert detail["inputs"]["cac_shock"] == 40
    assert detail["inputs"]["currency"] == "USD"
    assert detail["business"] == "Round trip"
    assert detail["result"]["grit_score"] == sent["grit_score"]
    assert detail["quality_score"] == sent["data_quality"]["score"]


def test_null_runway_stored_as_null(temp_db):
    sent = analyse()  # profitable -> no cash burn
    detail = api.get(f"/api/scenarios/{sent['scenario_id']}").json()
    assert detail["runway_months"] is None


def test_unknown_scenario_is_404(temp_db):
    r = api.get("/api/scenarios/999")
    assert r.status_code == 404
    assert "999" in r.json()["detail"]


def test_tests_never_touch_the_real_database():
    # The autouse temp_db fixture overrides get_db for every test
    assert db.get_db in main.app.dependency_overrides
