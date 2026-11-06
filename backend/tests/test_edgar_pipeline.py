"""Fix 5: ETL run on the frozen fixtures (trimmed real SEC data) into a temp DB, then every EDGAR API route."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import db
import main
from etl import edgar_ingest, report

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
TICKERS = ["PTON", "LOVE", "HIMS"]

api = TestClient(main.app)


@pytest.fixture
def loaded(temp_db, tmp_path):
    stats = edgar_ingest.run(TICKERS + ["NOPE"], raw_dir=FIXTURES, session_factory=temp_db,
                             write_docs=True, docs_dir=tmp_path)
    return stats, temp_db, tmp_path


def by_ticker(stats, t):
    return next(c for c in stats["companies"] if c["ticker"] == t)


# ---------- ETL on real (trimmed) data ----------

def test_companies_loaded_and_missing_one_skipped_with_reason(loaded):
    stats, _s, _p = loaded
    assert [c["ticker"] for c in stats["companies"]] == TICKERS
    assert "NOPE" in stats["skipped"] and "raw" in stats["skipped"]["NOPE"]


def test_peloton_june_fiscal_year_q4_derived_and_aligned(loaded):
    stats, Session, _p = loaded
    with Session() as s:
        q = s.scalar(select(db.QuarterlyFinancial).join(db.Company)
                     .where(db.Company.ticker == "PTON", db.QuarterlyFinancial.quarter == "2022-Q2"))
    # Fiscal Q4 (Apr-Jun 2022) of a June year: labelled by period end -> 2022-Q2
    assert (q.period_start.isoformat(), q.period_end.isoformat()) == ("2022-04-01", "2022-06-30")
    assert q.detail["operating_cash_flow"]["method"] == "q4_from_fy"
    assert q.operating_cash_flow == -342_200_000
    assert by_ticker(stats, "PTON")["fiscal_year_end"] == "06-30"


def test_peloton_restatements_recorded_with_kind(loaded):
    stats, Session, _p = loaded
    with Session() as s:
        r = s.scalar(select(db.Restatement).join(db.Company).where(
            db.Company.ticker == "PTON", db.Restatement.concept == "revenue",
            db.Restatement.original_value == 1_262_300_000))
    assert r.restated_value == 1_262_200_000 and r.kind == "rounding"
    assert by_ticker(stats, "PTON")["restatements_by_kind"]["restatement"] > 0


def test_hims_spac_shell_filings_dropped_and_cash_from_operating_company(loaded):
    stats, Session, _p = loaded
    h = by_ticker(stats, "HIMS")
    assert h["first_revenue_filing"] == "2021-05-17"
    assert h["dropped_pre_first_revenue_filing"] > 0
    assert h["dropped_forms"].get("8-K", 0) > 0
    with Session() as s:
        q = s.scalar(select(db.QuarterlyFinancial).join(db.Company)
                     .where(db.Company.ticker == "HIMS", db.QuarterlyFinancial.quarter == "2020-Q1"))
    # The shell's 10-Q said $1.48M; the operating company's later filing reports $55.2M
    assert q.cash == 55_165_000
    assert q.detail["cash"]["tag"] == "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"


def test_lovesac_inventory_and_revenue_tag_variants_logged(loaded):
    stats, _s, _p = loaded
    v = by_ticker(stats, "LOVE")["tag_variants"]
    assert set(v["inventory"]) == {"InventoryNet", "RetailRelatedInventoryMerchandise"}
    assert len(v["revenue"]) == 2


def test_normalised_tables_populated_with_provenance(loaded):
    _stats, Session, _p = loaded
    with Session() as s:
        n_facts = s.scalar(select(func.count()).select_from(db.FinancialFact))
        derived = s.scalar(select(func.count()).select_from(db.FinancialFact).where(db.FinancialFact.provenance == "DERIVED"))
        real_without_filing = s.scalar(select(func.count()).select_from(db.FinancialFact).where(
            db.FinancialFact.provenance == "REAL", db.FinancialFact.filing_id.is_(None)))
        assert s.scalar(select(func.count()).select_from(db.Filing)) > 0
        assert s.scalar(select(func.count()).select_from(db.EtlRun)) == 1
    assert n_facts > 0 and derived > 0
    assert real_without_filing == 0     # every reported value links to its filing


def test_etl_is_idempotent(loaded, temp_db):
    _stats, Session, _p = loaded
    with Session() as s:
        before = s.scalar(select(func.count()).select_from(db.FinancialFact))
    edgar_ingest.run(TICKERS, raw_dir=FIXTURES, session_factory=temp_db, write_docs=False)
    with Session() as s:
        assert s.scalar(select(func.count()).select_from(db.FinancialFact)) == before
        assert s.scalar(select(func.count()).select_from(db.Company)) == 3


def test_docs_and_dataset_facts_generated(loaded):
    stats, _s, docs = loaded
    profile = (docs / "EDGAR_PROFILE.md").read_text(encoding="utf-8")
    validation_md = (docs / "VALIDATION.md").read_text(encoding="utf-8")
    assert "## PTON" in profile and "DATASET FACTS" in profile
    assert "Why the numbers differ" in validation_md
    facts = report.dataset_facts(stats)
    for label in ("Companies loaded", "Restatements found", "Q4 values derived", "YTD -> quarter",
                  "Coverage", "Validation", "Top data-quality issues"):
        assert label in facts


def test_validation_computed_on_fixtures(loaded):
    stats, _s, _p = loaded
    v = stats["validation"]["overall"]
    assert v["quarters"] > 0
    assert v["median_abs_error_pct_revenue_after_addback"] is not None
    assert set(stats["validation"]["by_company"]) <= set(TICKERS)


# ---------- API ----------

def test_api_companies_and_quarters(loaded):
    companies = api.get("/api/companies").json()
    assert [c["ticker"] for c in companies] == ["HIMS", "LOVE", "PTON"]
    assert all(c["currency"] == "USD" and c["quarters"] > 0 for c in companies)
    quarters = api.get("/api/companies/pton/quarters").json()   # ticker is case-insensitive
    assert quarters[0]["quarter"] == "2019-Q2"
    assert "REAL" in quarters[0]["provenance_mix"]
    assert api.get("/api/companies/XXXX/quarters").status_code == 404


def test_api_analyze_company_quarter_full_pipeline(loaded, monkeypatch):
    r = api.post("/api/analyze/company/HIMS", params={"quarter": "2021-Q4"}, json={"rev_shock": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["company"]["ticker"] == "HIMS" and body["currency"] == "USD"
    assert body["inputs"]["revenue"] == pytest.approx(84_699_000 / 3)     # derived Q4 revenue / 3
    assert body["provenance"]["revenue"]["status"] == "DERIVED"
    assert {"provenance", "source"} <= set(body["data_quality"]["dimensions"])
    assert body["simulation"]["rev"] == pytest.approx(84_699_000 / 3 * 0.5)
    hist = api.get("/api/history").json()[0]
    assert (hist["source"], hist["ticker"], hist["period_label"]) == ("edgar", "HIMS", "2021-Q4")


@pytest.mark.parametrize(
    "ticker, params, body, status",
    [
        ("HIMS", {"quarter": "2021-13"}, None, 422),           # bad quarter format
        ("HIMS", {}, None, 422),                                # quarter required
        ("HIMS", {"quarter": "1999-Q1"}, None, 404),            # no data for that quarter
        ("XXXX", {"quarter": "2021-Q1"}, None, 404),            # unknown company
        ("HIMS", {"quarter": "2021-Q1"}, {"rev_shock": 150}, 422),   # shock out of range
        ("HIMS", {"quarter": "2021-Q1"}, {"revenue": 1}, 422),       # inputs come from filings, not the body
    ],
)
def test_api_analyze_company_invalid(loaded, ticker, params, body, status):
    assert api.post(f"/api/analyze/company/{ticker}", params=params, json=body).status_code == status


def test_api_validation(loaded):
    all_ = api.get("/api/validation").json()
    one = api.get("/api/validation", params={"ticker": "LOVE"}).json()
    assert all_["overall"]["quarters"] >= one["overall"]["quarters"] > 0
    assert {r["ticker"] for r in one["rows"]} == {"LOVE"}
    assert api.get("/api/validation", params={"ticker": "XXXX"}).status_code == 404


def test_api_without_etl_returns_empty_lists():
    assert api.get("/api/companies").json() == []
    assert api.get("/api/validation").json()["overall"] == {"quarters": 0}
