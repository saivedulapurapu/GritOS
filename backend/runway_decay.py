"""
Component 5: Runway-decay estimate over a 6-month horizon.

A transparent heuristic: an estimate of staying solvent derived from runway.
It is NOT survival analysis and is not fitted to any failure data.

Model: constant-hazard (exponential) decay with mean λ:
    estimate(month t) = exp(-t / λ) x 100

λ is the effective runway: the SHOCKED runway multiplied by the BASELINE
fragility tier's runway_factor (fragility_model.TIERS, always <= 1.0).
Hence λ <= runway: no tier can make a business outlast its cash.

Shock sensitivity is deliberately NOT part of λ: the shock already acts through
the shocked runway, so subtracting a sensitivity term would count it twice.
Sensitivity is reported as its own metric instead.

No cash burn (runway None) -> MAX_ESTIMATE: the estimate never claims certainty.

KNOWN CONSERVATIVE BIAS: a constant hazard spreads failure risk evenly over
every month, including months the cash arithmetic says are safe. A business
with exactly 12 months of runway (Stable/Resilient, λ = 12) gets
exp(-6 / 12) = 60.7% at month 6, although on current numbers it cannot run
out of cash before month 12. The estimate therefore understates short-horizon
solvency for long runways. By construction it never exceeds the decay implied
by face-value runway, so the bias only ever points towards caution.
"""
import math

from fragility_model import TIERS

HORIZON_MONTHS = 6
MAX_ESTIMATE = 99.9


def effective_runway(runway_months, tier):
    """Runway the estimate treats as usable: runway x tier factor (<= runway).
    None (no cash burn) stays None."""
    if runway_months is None:
        return None
    return max(0.0, float(runway_months)) * TIERS[tier]["runway_factor"]


def decay_estimate_at(month, runway_months, tier):
    """Runway-decay estimate (%) at `month`, rounded to 1 dp."""
    lam = effective_runway(runway_months, tier)
    if lam is None:
        return MAX_ESTIMATE
    if lam == 0:
        return 0.0
    return round(min(MAX_ESTIMATE, math.exp(-month / lam) * 100), 1)


def calculate_runway_decay_estimate(runway_months, tier):
    """Runway-decay estimate (%) at the 6-month horizon."""
    return decay_estimate_at(HORIZON_MONTHS, runway_months, tier)


def calculate_runway_decay_trajectory(runway_months, tier):
    """Month-by-month runway-decay curve for months 1..6."""
    return [
        {"name": f"Month {t}", "prob": decay_estimate_at(t, runway_months, tier)}
        for t in range(1, HORIZON_MONTHS + 1)
    ]
