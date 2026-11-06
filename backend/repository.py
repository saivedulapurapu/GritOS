"""Read/write analyses to the database. Keeps SQL out of main.py."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db import Business, QualityIssue, Result, Scenario

INPUT_FIELDS = [
    "currency", "revenue", "ad_spend", "cogs", "shipping_cost", "rto_cost", "fixed_costs",
    "cash_in_bank", "stock_units", "cost_per_unit", "daily_velocity", "top_platform_rev",
    "top_supplier_spend", "total_purchases", "cac_shock", "rev_shock", "cogs_shock", "ad_spend_behaviour",
]


def list_inputs(state):
    """List-valued inputs (concentration shares) are stored as JSON on the scenario."""
    extra = {k: getattr(state, k) for k in ("platform_shares", "supplier_shares") if getattr(state, k)}
    return extra or None


def get_or_create_business(db: Session, name, source="manual", ticker=None):
    business = db.scalar(select(Business).where(Business.name == name, Business.source == source))
    if business is None:
        business = Business(name=name, source=source, ticker=ticker)
        db.add(business)
        db.flush()
    return business


def save_analysis(db: Session, state, analysis, business_name, source="manual", ticker=None,
                  period_label=None, extra_inputs=None):
    """Persist scenario + result + quality issues in one transaction; returns the scenario id."""
    business = get_or_create_business(db, business_name, source, ticker)
    scenario = Scenario(
        business=business,
        period_label=period_label,
        extra_inputs=extra_inputs,
        **{f: getattr(state, f) for f in INPUT_FIELDS},
    )
    dq = analysis["data_quality"]
    result = Result(
        scenario=scenario,
        grit_score=analysis["grit_score"],
        baseline_grit=analysis["baseline_grit"],
        runway_decay_estimate=analysis["runway_decay_estimate"],
        baseline_runway_decay_estimate=analysis["baseline_runway_decay_estimate"],
        runway_months=analysis["baseline"]["runway_months"],
        shocked_runway_months=analysis["simulation"]["runway"],
        fragility_tier=analysis["fragility"]["class"],
        stressed_tier=analysis["fragility"]["stressed_class"],
        sensitivity=analysis["fragility"]["sensitivity"],
        quality_score=dq["score"],
        payload=analysis,
    )
    result.quality_issues = [
        QualityIssue(dimension=i["dimension"], code=i["code"], severity=i["severity"],
                     field=i.get("field"), message=i["message"])
        for i in dq["issues"]
    ]
    db.add(scenario)
    db.commit()
    return scenario.id


def _summary(scenario: Scenario):
    r = scenario.result
    return {
        "scenario_id": scenario.id,
        "created_at": scenario.created_at.isoformat(),
        "business": scenario.business.name,
        "source": scenario.business.source,
        "ticker": scenario.business.ticker,
        "period_label": scenario.period_label,
        "currency": scenario.currency,
        "shocks": {"cac_shock": scenario.cac_shock, "rev_shock": scenario.rev_shock,
                   "cogs_shock": scenario.cogs_shock, "ad_spend_behaviour": scenario.ad_spend_behaviour},
        "grit_score": r.grit_score,
        "baseline_grit": r.baseline_grit,
        "runway_decay_estimate": r.runway_decay_estimate,
        "runway_months": r.runway_months,
        "shocked_runway_months": r.shocked_runway_months,
        "fragility_tier": r.fragility_tier,
        "stressed_tier": r.stressed_tier,
        "quality_score": r.quality_score,
        "quality_issue_count": len(r.quality_issues),
    }


def list_history(db: Session, limit=50, business=None):
    q = (
        select(Scenario)
        .options(selectinload(Scenario.result).selectinload(Result.quality_issues), selectinload(Scenario.business))
        .order_by(Scenario.created_at.desc(), Scenario.id.desc())
        .limit(limit)
    )
    if business:
        q = q.join(Scenario.business).where(Business.name == business)
    return [_summary(s) for s in db.scalars(q)]


def get_scenario(db: Session, scenario_id):
    s = db.get(Scenario, scenario_id)
    if s is None:
        return None
    return {
        **_summary(s),
        "inputs": {f: getattr(s, f) for f in INPUT_FIELDS},
        "extra_inputs": s.extra_inputs,
        "result": s.result.payload,
        "quality_issues": [
            {"dimension": i.dimension, "code": i.code, "severity": i.severity, "field": i.field, "message": i.message}
            for i in s.result.quality_issues
        ],
    }
