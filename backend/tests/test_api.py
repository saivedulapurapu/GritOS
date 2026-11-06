"""Fix 1: API-level checks via FastAPI's in-process TestClient (no server, no Groq)."""
import pytest
from fastapi.testclient import TestClient

import main

api = TestClient(main.app)

BASE = {
    "revenue": 1_000_000,
    "ad_spend": 300_000,
    "cogs": 400_000,
    "shipping_cost": 50_000,
    "rto_cost": 20_000,
    "fixed_costs": 150_000,
    "cash_in_bank": 500_000,
}


def test_chat_rejects_empty_messages_with_422():
    r = api.post("/api/chat", json={"messages": [], "state": BASE})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "messages"]


def test_analyze_serialises_no_burn_runway_as_null(monkeypatch):
    monkeypatch.setattr(main.llm_advisor, "generate_strategic_advice", lambda metrics: ["stub"])
    # 100% ad-cost spike: ads 600,000 -> contribution -70,000 -> net -220,000
    # shocked runway = 500,000 / 220,000 = 2.27; baseline net +80,000 -> no burn -> null
    r = api.post("/api/analyze", json={**BASE, "cac_shock": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["baseline"]["runway_months"] is None
    assert body["simulation"]["runway"] == pytest.approx(2.27)
    # (12 - 2.27) / 100 = 0.0973 -> 0.097
    assert body["fragility"]["sensitivity"] == pytest.approx(0.097)
    assert body["advice"] == ["stub"]
