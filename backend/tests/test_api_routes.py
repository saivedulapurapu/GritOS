"""Fix 7: remaining API routes, the mock generator and the ETL command line (replaces test_gritos.py)."""
import random

import pytest
from fastapi.testclient import TestClient

import llm_advisor
import main
import mock_data
from etl import edgar_ingest
from schemas import FullBusinessState

api = TestClient(main.app)


@pytest.fixture(autouse=True)
def stub_advice(monkeypatch):
    monkeypatch.setattr(main.llm_advisor, "generate_strategic_advice", lambda metrics: ["stub"])


def test_health_check():
    assert api.get("/").json() == {"status": "online", "version": "2.0"}


@pytest.mark.parametrize("seed", range(30))
def test_mock_business_always_passes_the_schema_and_analyses(seed):
    # The old test_gritos.py smoke script did mock -> analyze against a live server; this covers
    # every branch of the generator (growth / stable / fragile) in-process.
    random.seed(seed)
    biz = api.get("/api/mock").json()
    FullBusinessState(**biz)                       # schema-valid (cross-field rules included)
    r = api.post("/api/analyze", json={**biz, "cac_shock": 20, "rev_shock": 10})
    assert r.status_code == 200, r.text
    assert 0 <= r.json()["grit_score"] <= 100


def test_mock_generator_covers_all_three_profiles():
    seen = set()
    for seed in range(60):
        random.seed(seed)
        biz = mock_data.generate_mock_business()
        seen.add("fragile" if biz["cash_in_bank"] < 300_000 else "other")
    assert seen == {"fragile", "other"}


def test_chat_streams_reply_with_fake_llm(monkeypatch):
    class Fake:
        def __init__(self):
            from types import SimpleNamespace
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kw):
            from types import SimpleNamespace
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t))])
                         for t in ("Cut ", "burn.")])

    monkeypatch.setattr(llm_advisor, "client", Fake())
    state = {"revenue": 1000, "ad_spend": 100, "cogs": 400, "shipping_cost": 50, "fixed_costs": 300,
             "cash_in_bank": 5000}
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "help"}], "state": state})
    assert r.status_code == 200 and r.text == "Cut burn."


def test_chat_without_key_returns_clear_message():
    state = {"revenue": 1000, "ad_spend": 100, "cogs": 400, "shipping_cost": 50, "fixed_costs": 300,
             "cash_in_bank": 5000}
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "help"}], "state": state})
    assert r.status_code == 200 and "Groq API key not configured" in r.text


def test_chat_rejects_invalid_state():
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "state": {"revenue": -1}})
    assert r.status_code == 422


# ---------- ETL command line ----------

def test_cli_requires_an_action():
    with pytest.raises(SystemExit):
        edgar_ingest.main([])


def test_cli_passes_tickers_and_prints_dataset_facts(monkeypatch, capsys):
    calls = {}

    def fake_run(tickers, fetch, refresh):
        calls.update(tickers=tickers, fetch=fetch, refresh=refresh)
        return {"companies": [], "skipped": {}, "validation": {"overall": {"quarters": 0}}}

    monkeypatch.setattr(edgar_ingest, "run", fake_run)
    edgar_ingest.main(["--load", "--tickers", "pton, love"])
    assert calls == {"tickers": ["PTON", "LOVE"], "fetch": False, "refresh": False}
    assert "DATASET FACTS" in capsys.readouterr().out


def test_fetch_without_user_agent_fails_before_any_request(monkeypatch, tmp_path):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        edgar_ingest.run(["PTON"], raw_dir=tmp_path, fetch=True)


# ---------- CORS (Fix 8) ----------

def test_cors_allows_configured_frontend_only():
    ok = api.options("/api/analyze", headers={"Origin": "http://localhost:3000",
                                              "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-credentials" not in ok.headers
    bad = api.options("/api/analyze", headers={"Origin": "https://evil.example",
                                               "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_allowed_origins_from_env_never_wildcard(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example, *, http://localhost:3000")
    assert main.allowed_origins() == ["https://app.example", "http://localhost:3000"]
