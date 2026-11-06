"""API routes for SEC EDGAR companies (data loaded by etl/edgar_ingest.py)."""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select

import data_quality
import db
import repository
from etl import validation
from etl.edgar_to_gritos import map_quarter, source_checks
from etl.validation import row_as_dict
from pipeline import process_business_state
from schemas import CompanyScenario, FullBusinessState

router = APIRouter(prefix="/api")

QUARTER_PATTERN = r"^\d{4}-Q[1-4]$"


def _company_or_404(session, ticker):
    company = session.scalar(select(db.Company).where(db.Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company {ticker.upper()} not loaded (run the EDGAR ETL)")
    return company


@router.get("/companies")
def list_companies(session=Depends(db.get_db)):
    q = (
        select(db.Company, func.count(db.QuarterlyFinancial.id), func.min(db.QuarterlyFinancial.quarter),
               func.max(db.QuarterlyFinancial.quarter))
        .join(db.QuarterlyFinancial, db.QuarterlyFinancial.company_id == db.Company.id, isouter=True)
        .group_by(db.Company.id)
        .order_by(db.Company.ticker)
    )
    restated = dict(session.execute(
        select(db.Restatement.company_id, func.count()).group_by(db.Restatement.company_id)).all())
    return [
        {"ticker": c.ticker, "cik": c.cik, "name": c.name, "currency": c.currency,
         "fiscal_year_end": c.fiscal_year_end, "quarters": n, "first_quarter": first, "last_quarter": last,
         "restatements": restated.get(c.id, 0)}
        for c, n, first, last in session.execute(q)
    ]


@router.get("/companies/{ticker}/quarters")
def list_quarters(ticker: str, session=Depends(db.get_db)):
    company = _company_or_404(session, ticker)
    rows = session.scalars(select(db.QuarterlyFinancial).where(db.QuarterlyFinancial.company_id == company.id)
                           .order_by(db.QuarterlyFinancial.quarter))
    out = []
    for q in rows:
        m = map_quarter(row_as_dict(q), company.name)
        out.append({"quarter": q.quarter, "period_start": q.period_start, "period_end": q.period_end,
                    "analysable": m["analysable"], "missing": m["missing"], "provenance_mix": m["provenance_mix"],
                    "revenue": q.revenue, "operating_income": q.operating_income, "cash": q.cash})
    return out


def _quarter_restatements(session, company, q):
    rows = session.scalars(select(db.Restatement).where(
        db.Restatement.company_id == company.id,
        db.Restatement.period_end >= (q.period_start or q.period_end),
        db.Restatement.period_end <= q.period_end,
    ))
    return [{"kind": r.kind, "concept": r.concept, "period_end": r.period_end.isoformat(),
             "original_value": r.original_value, "restated_value": r.restated_value} for r in rows]


@router.post("/analyze/company/{ticker}")
def analyze_company(
    ticker: str,
    quarter: str = Query(..., pattern=QUARTER_PATTERN, description="YYYY-Qn, by period end date"),
    scenario: CompanyScenario | None = Body(None),
    session=Depends(db.get_db),
):
    company = _company_or_404(session, ticker)
    q = session.scalar(select(db.QuarterlyFinancial).where(
        db.QuarterlyFinancial.company_id == company.id, db.QuarterlyFinancial.quarter == quarter))
    if q is None:
        raise HTTPException(status_code=404, detail=f"No data for {company.ticker} {quarter}")
    row = row_as_dict(q)
    mapping = map_quarter(row, company.name)
    if not mapping["analysable"]:
        raise HTTPException(status_code=422, detail={"message": f"{company.ticker} {quarter} cannot be analysed",
                                                     "missing": mapping["missing"]})
    scenario = scenario or CompanyScenario()
    if scenario.platform_shares or scenario.supplier_shares:
        mapping["provenance"]["concentration"] = {
            "status": "ASSUMED", "note": "entered manually (not in SEC companyfacts)"}
    state = FullBusinessState(**mapping["inputs"], **scenario.model_dump())
    analysis = process_business_state(state)

    report = data_quality.assess_manual_inputs(state, analysis)
    data_quality.assess_edgar(report, mapping, source_checks(row, _quarter_restatements(session, company, q)))
    analysis["data_quality"] = report.to_dict()

    scenario_id = repository.save_analysis(session, state, analysis, company.name, source="edgar",
                                           ticker=company.ticker, period_label=quarter,
                                           extra_inputs=repository.list_inputs(state))
    return {
        **analysis,
        "scenario_id": scenario_id,
        "company": {"ticker": company.ticker, "name": company.name, "cik": company.cik},
        "quarter": quarter,
        "period": {"start": q.period_start, "end": q.period_end},
        "inputs": mapping["inputs"],
        "provenance": mapping["provenance"],
        "provenance_mix": mapping["provenance_mix"],
        "adjustments": mapping["adjustments"],
        "reported": {"operating_cash_flow": q.operating_cash_flow, "share_based_comp": q.share_based_comp,
                     "depreciation_amortization": q.depreciation_amortization,
                     "operating_income": q.operating_income},
    }


@router.get("/validation")
def get_validation(ticker: str | None = None, session=Depends(db.get_db)):
    if ticker:
        _company_or_404(session, ticker)
    return validation.load_summary(session, ticker.upper() if ticker else None)
