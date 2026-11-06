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
    supplied = [f for f in OPTIONAL_INPUTS if f in state.model_fields_set]
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
