"""
Validation: does the GritOS engine's monthly net match reported cash generation?

For every analysable company-quarter with reported operating cash flow (OCF):
    gritos_monthly_net = net_profit from process_business_state on the mapped inputs
                         (negative = monthly cash burn)
    ocf_monthly        = OCF / 3
    error              = gritos_monthly_net - ocf_monthly
                         (negative = GritOS shows more burn than the cash-flow statement)

Expected gaps (why the model's net is not cash flow):
  - stock-based compensation and D&A are expenses but not cash  -> GritOS too pessimistic
  - working-capital swings (inventory build, payables timing)    -> either direction
  - interest, taxes and other items below operating income       -> small
The add-back check recomputes the error after adding (SBC + D&A) / 3 back to the GritOS net.
"""
from statistics import mean, median

from sqlalchemy import delete, select

import db


def compute_and_store(session):
    from etl.edgar_to_gritos import map_quarter
    from pipeline import process_business_state
    from schemas import FullBusinessState

    session.execute(delete(db.ValidationResult))
    companies = {c.id: c for c in session.scalars(select(db.Company))}
    rows = []
    for q in session.scalars(select(db.QuarterlyFinancial).order_by(db.QuarterlyFinancial.quarter)):
        company = companies[q.company_id]
        if q.operating_cash_flow is None:
            continue
        mapped = map_quarter(row_as_dict(q), company.name)
        if not mapped["analysable"]:
            continue
        analysis = process_business_state(FullBusinessState(**mapped["inputs"]))
        addback = None
        if q.share_based_comp is not None and q.depreciation_amortization is not None:
            addback = (q.share_based_comp + q.depreciation_amortization) / 3
        result = db.ValidationResult(
            company_id=q.company_id, quarter=q.quarter,
            gritos_monthly_net=analysis["baseline"]["net_profit"],
            ocf_monthly=q.operating_cash_flow / 3,
            revenue_monthly=q.revenue / 3,
            noncash_addback_monthly=addback,
        )
        session.add(result)
        rows.append({"ticker": company.ticker, "quarter": q.quarter, **_row_metrics(result)})
    session.flush()
    return summarize(rows)


def row_as_dict(q):
    return {c.name: getattr(q, c.name) for c in db.QuarterlyFinancial.__table__.columns}


def _row_metrics(r):
    err = r.gritos_monthly_net - r.ocf_monthly
    out = {
        "gritos_monthly_net": round(r.gritos_monthly_net, 2),
        "ocf_monthly": round(r.ocf_monthly, 2),
        "revenue_monthly": round(r.revenue_monthly, 2),
        "error": round(err, 2),
        "abs_error_pct_revenue": round(100 * abs(err) / r.revenue_monthly, 2) if r.revenue_monthly else None,
        "sign_agrees": (r.gritos_monthly_net >= 0) == (r.ocf_monthly >= 0),
        "error_after_addback": None,
    }
    if r.noncash_addback_monthly is not None:
        out["error_after_addback"] = round(err + r.noncash_addback_monthly, 2)
    return out


def summarize(rows):
    def block(rs):
        if not rs:
            return {"quarters": 0}
        errs = [r["error"] for r in rs]
        pct = [r["abs_error_pct_revenue"] for r in rs if r["abs_error_pct_revenue"] is not None]
        adj = [r for r in rs if r["error_after_addback"] is not None]
        adj_pct = [100 * abs(r["error_after_addback"]) / r["revenue_monthly"] for r in adj if r["revenue_monthly"]]
        return {
            "quarters": len(rs),
            "mae_usd_monthly": round(mean(abs(e) for e in errs), 0),
            "mean_abs_error_pct_revenue": round(mean(pct), 1) if pct else None,
            "median_abs_error_pct_revenue": round(median(pct), 1) if pct else None,
            "mean_error_usd_monthly": round(mean(errs), 0),
            "gritos_more_pessimistic_pct": round(100 * sum(e < 0 for e in errs) / len(errs), 1),
            "sign_agreement_pct": round(100 * sum(r["sign_agrees"] for r in rs) / len(rs), 1),
            "mean_abs_error_pct_revenue_after_addback": round(mean(adj_pct), 1) if adj_pct else None,
            "median_abs_error_pct_revenue_after_addback": round(median(adj_pct), 1) if adj_pct else None,
        }

    by_company = {}
    for r in rows:
        by_company.setdefault(r["ticker"], []).append(r)
    return {
        "overall": block(rows),
        "by_company": {t: block(rs) for t, rs in sorted(by_company.items())},
        "rows": rows,
    }


def load_summary(session, ticker=None):
    """Recompute the summary from stored validation_results (used by GET /api/validation)."""
    q = select(db.ValidationResult, db.Company.ticker).join(db.Company, db.Company.id == db.ValidationResult.company_id)
    if ticker:
        q = q.where(db.Company.ticker == ticker)
    rows = [{"ticker": t, "quarter": r.quarter, **_row_metrics(r)} for r, t in session.execute(q.order_by(db.ValidationResult.quarter))]
    return summarize(rows)
