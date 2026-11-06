"""
Grit Score (0-100): one headline number for resilience.

Grit is a pure function of a business state. baseline_grit applies it to the
unshocked figures; grit_score applies the SAME function to the stressed
scenario (stressed tier, scenario runway-decay estimate, shocked runway).
There is no separate ad-hoc shock penalty: a shock lowers Grit only by
changing the inputs.

    grit = (0.5 x tier score + 0.5 x runway-decay estimate)
           x concentration multiplier x inventory multiplier
    then capped at 40 if runway < 3 months

The weights are judgement calls, not fitted values: there is no outcome data
to fit them to. Each one is stated here so it can be challenged.

- 50 / 50 tier score vs runway-decay estimate. Two complementary views of one
  business: the tier scores how it is built (margin, liquidity bucket, ad
  dependence); the decay estimate scores how long the cash lasts. With no
  evidence to favour either, equal weights are the neutral choice and keep
  the effect readable: a 10-point move in either half moves Grit by 5.

- Concentration multiplier on the HHI (larger of platform and supplier HHI,
  dependency_index.py): x0.90 when moderately concentrated (1,500-2,500),
  x0.80 when highly concentrated (> 2,500) — the US DOJ/FTC 2010 bands.
  Concentration is a tail risk (platform ban, algorithm change, supplier
  failure) that the runway arithmetic cannot see. Multiplicative, so it scales
  with the base score; capped at a 20% haircut because it is a chance of a
  shock, not a certain loss.

- Inventory multiplier: x0.95 above 30 days to sell through, x0.85 above 60
  days or with no sales at all. Stock is cash that cannot be spent until it
  sells. The 30 / 60-day lines are the capital-lock risk levels, so the two
  features always agree.

- Cap at 40 when runway < 3 months. 40 is the UI boundary at or below which
  Grit reads "Critical", and 3 months is the fragility model's Critical
  runway line. A business that cannot last a quarter must never display
  better than Critical, whatever its margins or concentration profile.
"""
from fragility_model import CRITICAL_RUNWAY_MONTHS

TIER_WEIGHT = 0.5
DECAY_WEIGHT = 0.5

CONCENTRATION_HIGH_HHI = 2500      # > : highly concentrated
CONCENTRATION_MODERATE_HHI = 1500  # >= : moderately concentrated
CONCENTRATION_HIGH_MULT = 0.80
CONCENTRATION_MODERATE_MULT = 0.90

INVENTORY_SLOW_DAYS = 60
INVENTORY_WATCH_DAYS = 30
INVENTORY_SLOW_MULT = 0.85
INVENTORY_WATCH_MULT = 0.95

SHORT_RUNWAY_MONTHS = CRITICAL_RUNWAY_MONTHS  # 3
SHORT_RUNWAY_CAP = 40


def concentration_multiplier(concentration_hhi):
    if concentration_hhi > CONCENTRATION_HIGH_HHI:
        return CONCENTRATION_HIGH_MULT
    if concentration_hhi >= CONCENTRATION_MODERATE_HHI:
        return CONCENTRATION_MODERATE_MULT
    return 1.0


def inventory_multiplier(days_to_liquidate):
    """days_to_liquidate None = no sales velocity -> worst bucket."""
    if days_to_liquidate is None or days_to_liquidate > INVENTORY_SLOW_DAYS:
        return INVENTORY_SLOW_MULT
    if days_to_liquidate > INVENTORY_WATCH_DAYS:
        return INVENTORY_WATCH_MULT
    return 1.0


def compute_grit(tier_score, decay_estimate, concentration_hhi, days_to_liquidate, runway_months):
    """
    Grit for one business state.
    runway_months: runway of that state (None = no cash burn), used only for the cap.
    Returns the score plus every component, so the number can be explained.
    """
    base = TIER_WEIGHT * tier_score + DECAY_WEIGHT * decay_estimate
    conc = concentration_multiplier(concentration_hhi)
    inv = inventory_multiplier(days_to_liquidate)
    score = base * conc * inv

    short_runway = runway_months is not None and runway_months < SHORT_RUNWAY_MONTHS
    capped = short_runway and score > SHORT_RUNWAY_CAP
    if capped:
        score = SHORT_RUNWAY_CAP

    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "base": round(base, 1),
        "concentration_multiplier": conc,
        "inventory_multiplier": inv,
        "capped": capped,
    }
