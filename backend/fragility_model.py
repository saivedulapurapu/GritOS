"""
Component 6: Fragility tier — transparent rules.

Replaces a RandomForest trained on 7 hand-typed rows, which labelled a
1.35-month runway "Anti-Fragile". Seven rows cannot support a learned model;
explicit thresholds can be read, tested and challenged.

The baseline tier uses unshocked figures and describes the business's
structure; its runway_factor feeds the runway-decay estimate (runway_decay.py).
main.py also applies the same rules to the shocked figures to report a
STRESSED tier, so the UI never shows "Resilient" beside a collapsing scenario.

Thresholds are stated rules of thumb, not fitted to data:
- Runway 3 / 6 / 12 months: under 3 months there is no time to raise money or
  cut costs; 6 months is the usual "fundraise or cut now" line; 12+ months is
  a comfortable buffer.
- Contribution margin: <= 0% means every extra sale loses money, so growth
  deepens the burn; < 10% leaves no room for a price or cost shock; >= 20% is
  healthy for D2C.
- Ad spend / revenue: > 50% means the business depends on paid acquisition;
  <= 30% is required for Resilient.
- Concentration (HHI of platform or supplier shares, see dependency_index.py):
  highly concentrated (> 2,500) makes a business Fragile — one platform ban or
  supplier failure removes most of its sales or supply; Resilient requires an
  unconcentrated profile (< 1,500).
"""

# score:          feeds the Grit Score (unchanged scale: old Anti-Fragile 100,
#                 Sensitive 50, Critical 20; Stable is the new middle tier).
# runway_factor:  share of the computed runway the runway-decay estimate treats as
#                 usable. Always <= 1.0, so a tier can only SHORTEN runway.
TIERS = {
    # Negative unit economics or < 3 months cash: burn usually accelerates
    # (discounting, emergency spend, supplier terms tighten), so assume only
    # 60% of the arithmetic runway is really available.
    "Critical": {"color": "RED", "score": 20, "runway_factor": 0.6},
    # Thin margin, < 6 months cash or heavy ad dependence: a modest adverse
    # move shortens runway, so haircut it by 20%.
    "Fragile": {"color": "YELLOW", "score": 50, "runway_factor": 0.8},
    # Sound but not exceptional: take the runway at face value.
    "Stable": {"color": "GREEN", "score": 75, "runway_factor": 1.0},
    # Strong margins, long runway, low ad dependence. Still 1.0, never more:
    # no business outlasts its cash.
    "Resilient": {"color": "GREEN", "score": 100, "runway_factor": 1.0},
}

CRITICAL_RUNWAY_MONTHS = 3
FRAGILE_RUNWAY_MONTHS = 6
RESILIENT_RUNWAY_MONTHS = 12
FRAGILE_MARGIN_PCT = 10
RESILIENT_MARGIN_PCT = 20
FRAGILE_AD_RATIO = 0.5
RESILIENT_AD_RATIO = 0.3
FRAGILE_HHI = 2500       # DOJ/FTC "highly concentrated" above this
RESILIENT_HHI = 1500     # DOJ/FTC "unconcentrated" below this


def classify_fragility(margin_pct, runway_months, ad_spend_ratio, concentration_hhi=0.0):
    """
    Classify baseline business health into Critical / Fragile / Stable / Resilient.
    runway_months: baseline runway, None = no cash burn.
    concentration_hhi: larger of platform / supplier HHI (0 = not supplied).
    Returns the tier with its score, colour, runway_factor and the reasons for it.
    """
    burning = runway_months is not None

    critical = []
    if margin_pct <= 0:
        critical.append("Contribution margin is 0% or negative: each sale loses money")
    if burning and runway_months < CRITICAL_RUNWAY_MONTHS:
        critical.append(f"Runway under {CRITICAL_RUNWAY_MONTHS} months")
    if critical:
        return _result("Critical", critical)

    fragile = []
    if burning and runway_months < FRAGILE_RUNWAY_MONTHS:
        fragile.append(f"Runway under {FRAGILE_RUNWAY_MONTHS} months")
    if margin_pct < FRAGILE_MARGIN_PCT:
        fragile.append(f"Contribution margin under {FRAGILE_MARGIN_PCT}%")
    if ad_spend_ratio > FRAGILE_AD_RATIO:
        fragile.append(f"Ad spend over {FRAGILE_AD_RATIO:.0%} of revenue")
    if concentration_hhi > FRAGILE_HHI:
        fragile.append(f"Highly concentrated platforms or suppliers (HHI {concentration_hhi:,.0f} > {FRAGILE_HHI:,})")
    if fragile:
        return _result("Fragile", fragile)

    gaps = []
    if burning and runway_months < RESILIENT_RUNWAY_MONTHS:
        gaps.append(f"Runway under {RESILIENT_RUNWAY_MONTHS} months")
    if margin_pct < RESILIENT_MARGIN_PCT:
        gaps.append(f"Contribution margin under {RESILIENT_MARGIN_PCT}%")
    if ad_spend_ratio > RESILIENT_AD_RATIO:
        gaps.append(f"Ad spend over {RESILIENT_AD_RATIO:.0%} of revenue")
    if concentration_hhi >= RESILIENT_HHI:
        gaps.append(f"Moderately concentrated platforms or suppliers (HHI {concentration_hhi:,.0f} >= {RESILIENT_HHI:,})")
    if gaps:
        return _result("Stable", gaps)

    return _result("Resilient", ["Meets all resilient thresholds"])


def _result(tier, reasons):
    return {"class": tier, **TIERS[tier], "reasons": reasons}


# Runway beyond this horizon counts as "safe". Capping both runways here puts an
# infinite (None) runway on the same scale as a long finite one.
SENSITIVITY_HORIZON_MONTHS = 12.0


def get_shock_sensitivity(baseline_runway, shock_runway, total_shock_pct):
    """
    Component 7: Shock Sensitivity Score
    Formula: months of runway lost / total shock, where total shock is the sum of
    the revenue-drop, ad-cost and COGS shock percentages.
    Runways (None = no cash burn) are capped at SENSITIVITY_HORIZON_MONTHS.
    A shock that lengthens runway scores 0, never negative.
    """
    if total_shock_pct <= 0:
        return 0
    return round(_runway_lost(baseline_runway, shock_runway) / total_shock_pct, 3)


def _runway_lost(baseline_runway, shock_runway):
    horizon = SENSITIVITY_HORIZON_MONTHS
    b_val = horizon if baseline_runway is None else min(float(baseline_runway), horizon)
    s_val = horizon if shock_runway is None else min(float(shock_runway), horizon)
    return max(0.0, b_val - s_val)


def runway_lost_within_horizon(baseline_runway, shock_runway):
    """Months of runway lost, counting only the first 12 months (None = no burn).
    Same horizon as sensitivity, so 'months lost' and sensitivity always agree."""
    return round(_runway_lost(baseline_runway, shock_runway), 2)
