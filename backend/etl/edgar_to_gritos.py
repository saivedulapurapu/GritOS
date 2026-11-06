"""
Map one normalised company-quarter (quarterly_financials row) to GritOS inputs.
Every input carries a provenance status:

  REAL     reported for exactly this period; only averaged to a month (quarter / 3)
  DERIVED  computed from reported facts (Q4 = FY - (Q1+Q2+Q3), YTD differencing,
           operating expenses = revenue - COGS - operating income, annual -> monthly
           allocation, days of stock = inventory / (COGS / days))
  PROXY    a reported figure standing in for a different concept
           (marketing expense used as ad spend: it also contains non-advertising costs)
  ASSUMED  not in the data: a stated default (shipping, returns, concentration, units)
  MISSING  required and absent: the quarter cannot be analysed

Fixed costs. GritOS computes net = revenue - ad spend - COGS - shipping - returns - fixed.
SG&A is not comparable across companies (Honest reports marketing separately from SG&A,
Warby Parker includes it), so fixed costs are taken from the income statement identity:
    operating expenses = revenue - COGS - operating income
    fixed_costs        = operating expenses - ad spend
which preserves total operating expenses whatever the ad-spend source, so the GritOS
monthly net equals reported operating income / 3. It includes non-cash stock-based
compensation and D&A, which is why validation adds those back.
"""
from etl.edgar_ingest import CONCEPTS

STATUS_WEIGHT = {"REAL": 1.0, "DERIVED": 0.8, "PROXY": 0.5, "ASSUMED": 0.3, "MISSING": 0.0}
PRIMARY_TAG = {c: tags[0] for c, (_kind, tags) in CONCEPTS.items()}
METHOD_NOTE = {
    "reported": "reported quarter",
    "ytd_difference": "quarter derived by differencing year-to-date figures",
    "q4_from_fy": "Q4 derived as FY - (Q1 + Q2 + Q3)",
    "q4_from_fy_minus_9m": "Q4 derived as FY - 9 months YTD",
}
PROVENANCE_FIELDS = ["revenue", "cogs", "ad_spend", "fixed_costs", "shipping_cost", "rto_cost", "cash_in_bank",
                     "stock_units", "cost_per_unit", "daily_velocity", "concentration"]


def _status(q, concept):
    return (q.get("provenance") or {}).get(concept, "MISSING") if q.get(concept) is not None else "MISSING"


def _method(q, concept):
    return ((q.get("detail") or {}).get(concept) or {}).get("method", "reported")


def days_in_period(q):
    if q.get("period_start") and q.get("period_end"):
        return (q["period_end"] - q["period_start"]).days + 1
    return 91


def map_quarter(q, company_name):
    """q: dict with quarterly_financials columns (+ provenance, detail). Returns inputs + provenance."""
    prov, missing, adjustments = {}, [], []

    def flow(concept):
        status = _status(q, concept)
        if status == "MISSING":
            return None, status, f"{concept} not reported"
        note = f"{METHOD_NOTE.get(_method(q, concept), _method(q, concept))}; quarterly / 3 for monthly"
        return q[concept] / 3, status, note

    revenue, s, note = flow("revenue")
    prov["revenue"] = {"status": s, "note": note}
    cogs, s, note = flow("cogs")
    prov["cogs"] = {"status": s, "note": note}
    for name, value in (("revenue", revenue), ("cogs", cogs)):
        if value is None:
            missing.append(name)

    # Ad spend: annual AdvertisingExpense allocated evenly, else marketing expense as a PROXY
    if q.get("advertising_annual") is not None:
        ad_spend = q["advertising_annual"] / 12
        prov["ad_spend"] = {"status": "DERIVED",
                            "note": "fiscal-year AdvertisingExpense / 12 (assumes even spend through the year)"}
    elif q.get("marketing") is not None:
        ad_spend = q["marketing"] / 3
        prov["ad_spend"] = {"status": "PROXY",
                            "note": "marketing expense / 3: includes non-advertising marketing costs, so it overstates ad spend"}
    else:
        ad_spend = 0.0
        prov["ad_spend"] = {"status": "ASSUMED",
                            "note": "no advertising or marketing figure; all operating expenses are in fixed_costs"}

    # Fixed costs from the income statement identity (see module docstring)
    fixed = None
    if revenue is not None and cogs is not None and q.get("operating_income") is not None:
        opex_monthly = (q["revenue"] - q["cogs"] - q["operating_income"]) / 3
        if ad_spend > opex_monthly:
            adjustments.append(f"ad spend {ad_spend:,.0f} capped at monthly operating expenses {max(opex_monthly, 0):,.0f}")
            ad_spend = max(opex_monthly, 0.0)
        fixed = opex_monthly - ad_spend
        if fixed < 0:
            adjustments.append(f"negative operating expenses ({opex_monthly:,.0f}/month, e.g. gains); fixed_costs set to 0")
            fixed = 0.0
        prov["fixed_costs"] = {"status": "DERIVED",
                               "note": "(revenue - COGS - operating income) / 3 - ad spend; includes non-cash stock comp and D&A"}
    else:
        missing.append("fixed_costs")
        prov["fixed_costs"] = {"status": "MISSING", "note": "operating income not reported"}

    prov["shipping_cost"] = {"status": "ASSUMED", "note": "0: not separately tagged; included in COGS"}
    prov["rto_cost"] = {"status": "ASSUMED", "note": "0: returns are netted from revenue"}

    cash = q.get("cash")
    if cash is None:
        missing.append("cash_in_bank")
        prov["cash_in_bank"] = {"status": "MISSING", "note": "cash not reported at quarter end"}
    else:
        prov["cash_in_bank"] = {"status": _status(q, "cash"), "note": "cash and equivalents at quarter end"}

    # Inventory: counted in dollars at cost (1 unit = $1), velocity = COGS per day
    inventory = q.get("inventory")
    days = days_in_period(q)
    if inventory is not None and inventory > 0 and q.get("cogs"):
        stock_units, cost_per_unit, velocity = int(round(inventory)), 1.0, q["cogs"] / days
        prov["stock_units"] = {"status": "REAL", "note": "inventory at cost (USD), counted as $1 units"}
        prov["cost_per_unit"] = {"status": "ASSUMED", "note": "convention: 1 unit = $1 of inventory at cost"}
        prov["daily_velocity"] = {"status": "DERIVED", "note": f"quarterly COGS / {days} days"}
    else:
        stock_units, cost_per_unit, velocity = 0, 1.0, 0.0
        for f in ("stock_units", "cost_per_unit", "daily_velocity"):
            prov[f] = {"status": "ASSUMED", "note": "inventory not reported for this quarter; treated as none"}

    prov["concentration"] = {"status": "ASSUMED",
                             "note": "platform/supplier concentration is not in companyfacts; enter it manually"}

    inputs = None
    if not missing:
        inputs = {
            "business_name": company_name[:120],
            "currency": "USD",
            "revenue": revenue, "ad_spend": ad_spend, "cogs": cogs,
            "shipping_cost": 0.0, "rto_cost": 0.0, "fixed_costs": fixed, "cash_in_bank": cash,
            "stock_units": stock_units, "cost_per_unit": cost_per_unit, "daily_velocity": velocity,
        }
    return {
        "inputs": inputs,
        "provenance": prov,
        "analysable": not missing,
        "missing": missing,
        "adjustments": adjustments,
        "provenance_mix": provenance_mix(prov),
    }


def provenance_mix(prov):
    statuses = [prov[f]["status"] for f in PROVENANCE_FIELDS if f in prov]
    n = len(statuses) or 1
    return {s: round(100 * statuses.count(s) / n, 1) for s in STATUS_WEIGHT if statuses.count(s)}


def source_checks(q, restatements):
    """Facts about the source data behind this quarter, for the data-quality 'source' dimension."""
    derived = [c for c in ("revenue", "cogs", "operating_income")
               if q.get(c) is not None and _method(q, c) != "reported"]
    non_primary = [c for c, d in (q.get("detail") or {}).items()
                   if c in PRIMARY_TAG and d.get("tag") not in (None, PRIMARY_TAG[c])]
    missing_validation = [c for c in ("operating_cash_flow", "share_based_comp", "depreciation_amortization")
                          if q.get(c) is None]
    return {
        "derived_concepts": derived,
        "non_primary_tags": {c: q["detail"][c]["tag"] for c in non_primary},
        "restatements": restatements,
        "missing_validation_concepts": missing_validation,
    }
