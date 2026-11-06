"""Fix 3: hard validation rules (schemas.py) — every violation is a 422 with a clear message."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from schemas import ChatRequest, FullBusinessState

api = TestClient(main.app)

BASE = {
    "revenue": 1_000_000, "ad_spend": 300_000, "cogs": 400_000, "shipping_cost": 50_000,
    "rto_cost": 20_000, "fixed_costs": 150_000, "cash_in_bank": 500_000,
}


@pytest.fixture(autouse=True)
def stub_advice(monkeypatch):
    monkeypatch.setattr(main.llm_advisor, "generate_strategic_advice", lambda metrics: ["stub"])


def post(**overrides):
    return api.post("/api/analyze", json={**BASE, **overrides})


def messages(r):
    return " | ".join(e["msg"] for e in r.json()["detail"])


# ---------- ranges ----------

@pytest.mark.parametrize(
    "field", ["revenue", "ad_spend", "cogs", "shipping_cost", "rto_cost", "fixed_costs",
              "cash_in_bank", "stock_units", "cost_per_unit", "daily_velocity",
              "top_platform_rev", "top_supplier_spend", "total_purchases"],
)
def test_negative_money_and_quantities_rejected(field):
    r = post(**{field: -1})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", field]


def test_audit_case_negative_revenue_rejected():
    assert post(revenue=-500_000).status_code == 422


@pytest.mark.parametrize(
    "field, ok, bad",
    [("rev_shock", 100, 100.1), ("cac_shock", 300, 300.1), ("cogs_shock", 300, 301)],
)
def test_shock_bounds(field, ok, bad):
    assert post(**{field: ok}).status_code == 200
    assert post(**{field: bad}).status_code == 422
    assert post(**{field: -1}).status_code == 422


def test_audit_case_revenue_shock_500_rejected():
    assert post(rev_shock=500).status_code == 422


# ---------- cross-field ----------

def test_platform_revenue_cannot_exceed_revenue():
    # Audit case: top platform at 5x revenue
    r = post(top_platform_rev=5_000_000)
    assert r.status_code == 422
    assert "top_platform_rev" in messages(r) and "cannot exceed revenue" in messages(r)


def test_platform_revenue_equal_to_revenue_allowed():
    assert post(top_platform_rev=1_000_000).status_code == 200


def test_supplier_spend_cannot_exceed_total_purchases():
    r = post(top_supplier_spend=400_000, total_purchases=300_000)
    assert r.status_code == 422
    assert "top_supplier_spend" in messages(r)


def test_stock_without_velocity_rejected():
    r = post(stock_units=100, daily_velocity=0)
    assert r.status_code == 422
    assert "daily_velocity must be > 0" in messages(r)


def test_no_stock_and_no_velocity_allowed():
    assert post(stock_units=0, daily_velocity=0).status_code == 200


def test_several_cross_field_problems_reported_together():
    with pytest.raises(ValidationError) as e:
        FullBusinessState(**BASE, top_platform_rev=2_000_000, stock_units=5, daily_velocity=0)
    text = str(e.value)
    assert "top_platform_rev" in text and "daily_velocity" in text


# ---------- other schema rules ----------

def test_unknown_field_rejected_including_old_kak_shock():
    r = post(kak_shock=10)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "kak_shock"]


def test_missing_required_field_rejected():
    body = dict(BASE)
    del body["revenue"]
    assert api.post("/api/analyze", json=body).status_code == 422


def test_currency_defaults_to_inr_and_accepts_usd():
    assert FullBusinessState(**BASE).currency == "INR"
    assert post(currency="USD").json()["currency"] == "USD"
    assert post(currency="EUR").status_code == 422


def test_nan_and_infinity_rejected():
    with pytest.raises(ValidationError):
        FullBusinessState(**{**BASE, "revenue": float("nan")})
    with pytest.raises(ValidationError):
        FullBusinessState(**{**BASE, "cash_in_bank": float("inf")})


def test_chat_role_and_content_validated():
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "system", "content": "hi"}], state=BASE)
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "user", "content": ""}], state=BASE)


# ---------- the error response itself ----------

def test_validation_error_does_not_echo_request_body():
    secret_cash = 987_654_321
    r = post(cash_in_bank=secret_cash, revenue=-1)
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"detail"}
    assert str(secret_cash) not in r.text
    assert all(set(e) == {"loc", "msg", "type"} for e in body["detail"])


def test_validation_error_is_not_printed(capsys):
    post(revenue=-1, cash_in_bank=123_456_789)
    assert "123456789" not in capsys.readouterr().out
