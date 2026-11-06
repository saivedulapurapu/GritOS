"""
Data quality report for one analysis.

Hard rules (types, ranges, cross-field) are enforced by schemas.py and rejected
with 422, so every report here describes inputs that already passed them. This
module reports the softer problems, scored per dimension:

  completeness  optional inputs the model uses that were actually supplied
                (defaults are used otherwise, and the report says so)
  validity      soft validity: values that pass the schema but make parts of the
                model undefined (e.g. zero revenue makes every ratio 0)
  consistency   relationships between inputs that are possible but suspicious
                (ad spend or COGS above revenue)
  plausibility  outputs outside what real businesses report
                (margin > 90 %, finite runway > 120 months, > 365 days of stock)

Extension point: QualityReport.add() / set_score() accept any dimension name, so
the SEC EDGAR path adds 'provenance' (REAL / DERIVED / PROXY / ASSUMED mix) and
'source' (coverage gaps, restatements, derived periods) without changing this code.

Scoring — deliberately simple so it can be checked by hand:
  dimension score = max(0, 100 - sum of issue penalties)
      penalties: error 40, warning 20, info 5
  completeness    = 100 x supplied optional inputs / optional inputs
  overall score   = weighted mean of the dimensions present, weights renormalised
      weights: validity 0.30, consistency 0.25, plausibility 0.25, completeness 0.20,
               provenance 0.30, source 0.20 (the last two only on the EDGAR path)
"""

PENALTY = {"error": 40, "warning": 20, "info": 5}

WEIGHTS = {
    "validity": 0.30,
    "consistency": 0.25,
    "plausibility": 0.25,
    "completeness": 0.20,
    "provenance": 0.30,
    "source": 0.20,
}

# Inputs with defaults that the model uses (cash-flow inputs are required by the schema)
OPTIONAL_INPUTS = [
    "rto_cost",
    "stock_units",
    "cost_per_unit",
    "daily_velocity",
    "top_platform_rev",
    "top_supplier_spend",
    "total_purchases",
]

# A share list supplies the same information as the top-share fields
ALTERNATIVE_INPUTS = {"top_platform_rev": "platform_shares", "top_supplier_spend": "supplier_shares",
                      "total_purchases": "supplier_shares"}

MAX_PLAUSIBLE_MARGIN_PCT = 90
MIN_PLAUSIBLE_MARGIN_PCT = -100
MAX_PLAUSIBLE_RUNWAY_MONTHS = 120
MAX_PLAUSIBLE_DAYS_OF_STOCK = 365


class QualityReport:
    def __init__(self):
        self.issues = []
        self._scores = {}
        self._dimensions = []

    def touch(self, dimension):
        if dimension not in self._dimensions:
            self._dimensions.append(dimension)

    def add(self, dimension, code, severity, message, field=None):
        if severity not in PENALTY:
            raise ValueError(f"unknown severity {severity!r}")
        self.touch(dimension)
        self.issues.append(
            {"dimension": dimension, "code": code, "severity": severity, "field": field, "message": message}
        )

    def set_score(self, dimension, score):
        """Override the penalty-based score for a dimension (e.g. completeness as a ratio)."""
        self.touch(dimension)
        self._scores[dimension] = max(0.0, min(100.0, float(score)))

    def dimension_score(self, dimension):
        if dimension in self._scores:
            return self._scores[dimension]
        penalty = sum(PENALTY[i["severity"]] for i in self.issues if i["dimension"] == dimension)
        return float(max(0, 100 - penalty))

    def to_dict(self):
        dims = {}
        for d in self._dimensions:
            dims[d] = {
                "score": round(self.dimension_score(d), 1),
                "weight": WEIGHTS.get(d, 0.0),
                "issues": sum(1 for i in self.issues if i["dimension"] == d),
            }
        total_weight = sum(v["weight"] for v in dims.values())
        overall = (
            sum(v["score"] * v["weight"] for v in dims.values()) / total_weight if total_weight else 100.0
        )
        return {"score": round(overall, 1), "dimensions": dims, "issues": list(self.issues)}


def assess_manual_inputs(state, analysis, report=None):
    """Run the completeness / validity / consistency / plausibility checks.
    Returns the QualityReport so callers (EDGAR path) can add more dimensions."""
    report = report or QualityReport()

    # ---- completeness ----
    given = state.model_fields_set
    supplied = [f for f in OPTIONAL_INPUTS if f in given or ALTERNATIVE_INPUTS.get(f) in given]
    report.set_score("completeness", 100 * len(supplied) / len(OPTIONAL_INPUTS))
    for f in OPTIONAL_INPUTS:
        if f not in supplied:
            report.add("completeness", "default_used", "info", f"{f} not supplied; default used", f)

    # ---- validity (soft) ----
    report.touch("validity")
    if state.revenue == 0:
        report.add("validity", "zero_revenue", "warning",
                   "Revenue is 0: margin and ad-spend ratio are undefined and reported as 0", "revenue")
    if state.stock_units > 0 and state.cost_per_unit == 0:
        report.add("validity", "zero_unit_cost", "warning",
                   "Stock held but cost_per_unit is 0: locked capital is reported as 0", "cost_per_unit")

    # ---- consistency ----
    report.touch("consistency")
    if state.revenue > 0:
        if state.ad_spend > state.revenue:
            report.add("consistency", "ad_spend_exceeds_revenue", "warning",
                       "Ad spend is larger than revenue", "ad_spend")
        if state.cogs > state.revenue:
            report.add("consistency", "cogs_exceeds_revenue", "warning",
                       "COGS is larger than revenue: every sale loses money before other costs", "cogs")
        if state.shipping_cost + state.rto_cost > state.revenue:
            report.add("consistency", "logistics_exceed_revenue", "warning",
                       "Shipping + returns cost more than revenue", "shipping_cost")

    # ---- plausibility (outputs) ----
    report.touch("plausibility")
    margin = analysis["baseline"]["margin_percent"]
    if margin > MAX_PLAUSIBLE_MARGIN_PCT:
        report.add("plausibility", "margin_too_high", "warning",
                   f"Contribution margin {margin:.1f}% is above {MAX_PLAUSIBLE_MARGIN_PCT}%", "revenue")
    if margin < MIN_PLAUSIBLE_MARGIN_PCT:
        report.add("plausibility", "margin_too_low", "warning",
                   f"Contribution margin {margin:.1f}% is below {MIN_PLAUSIBLE_MARGIN_PCT}%", "revenue")
    runway = analysis["baseline"]["runway_months"]
    if runway is not None and runway > MAX_PLAUSIBLE_RUNWAY_MONTHS:
        report.add("plausibility", "runway_too_long", "warning",
                   f"Runway {runway:.0f} months is above {MAX_PLAUSIBLE_RUNWAY_MONTHS} months", "cash_in_bank")
    days = analysis["inventory"]["days_to_liquidate"]
    if days is not None and days > MAX_PLAUSIBLE_DAYS_OF_STOCK:
        report.add("plausibility", "stock_days_too_high", "warning",
                   f"{days:.0f} days to sell through current stock (> {MAX_PLAUSIBLE_DAYS_OF_STOCK})",
                   "stock_units")

    return report


def build_report(state, analysis):
    return assess_manual_inputs(state, analysis).to_dict()


# ---------------------------------------------------------------------------
# SEC EDGAR extension: provenance and source-data dimensions
# ---------------------------------------------------------------------------

# Credit given to each provenance status in the 'provenance' dimension score
PROVENANCE_CREDIT = {"REAL": 1.0, "DERIVED": 0.8, "PROXY": 0.5, "ASSUMED": 0.3, "MISSING": 0.0}


def assess_edgar(report, mapping, source):
    """Add 'provenance' and 'source' dimensions for an analysis built from SEC filings.

    provenance score = 100 x mean credit over the GritOS inputs
                       (REAL 1.0, DERIVED 0.8, PROXY 0.5, ASSUMED 0.3, MISSING 0)
    source score     = penalty-based: restated values (info), quarters derived from
                       FY / YTD figures (info), non-primary XBRL tag used (info),
                       mapping adjustments (warning), validation concepts missing (info)
    """
    prov = mapping["provenance"]
    credits = [PROVENANCE_CREDIT[p["status"]] for p in prov.values()]
    report.set_score("provenance", 100 * sum(credits) / len(credits) if credits else 0)
    for field, p in prov.items():
        if p["status"] in ("PROXY", "ASSUMED"):
            report.add("provenance", p["status"].lower(), "info", f"{field} is {p['status']}: {p['note']}", field)
        elif p["status"] == "MISSING":
            report.add("provenance", "missing", "warning", f"{field} is MISSING: {p['note']}", field)

    report.touch("source")
    for r in source.get("restatements", []):
        report.add("source", f"restated_{r['kind']}", "info",
                   f"{r['concept']} for {r['period_end']} was re-reported: {r['original_value']:,.0f} -> "
                   f"{r['restated_value']:,.0f} ({r['kind']}); latest filing used", r["concept"])
    for c in source.get("derived_concepts", []):
        report.add("source", "derived_period", "info",
                   f"{c} for this quarter is derived from annual / year-to-date figures", c)
    for c, tag in source.get("non_primary_tags", {}).items():
        report.add("source", "non_primary_tag", "info", f"{c} taken from fallback tag {tag}", c)
    for a in mapping.get("adjustments", []):
        report.add("source", "mapping_adjustment", "warning", a)
    for c in source.get("missing_validation_concepts", []):
        report.add("source", "validation_concept_missing", "info",
                   f"{c} not reported: burn-vs-cash-flow validation incomplete for this quarter", c)
    return report
