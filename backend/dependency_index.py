"""
Component 4: Concentration risk — Herfindahl-Hirschman Index (HHI).

    HHI = sum of squared shares, shares in percent (0-100)
        -> near 0 for many small sources, 10,000 for a single source

Bands (US DOJ / FTC Horizontal Merger Guidelines, 2010, section 5.3):
    HHI < 1,500          unconcentrated
    1,500 <= HHI <= 2,500  moderately concentrated
    HHI > 2,500          highly concentrated
The 2023 Merger Guidelines lowered the thresholds (1,000 / 1,800); GritOS uses the 2010 bands,
the long-standing reference, and says so here so the choice can be challenged.

Sources of shares, in order of preference:
  1. a list of shares (platform_shares / supplier_shares) -> exact HHI       (basis "shares")
  2. only the top source's amount -> HHI = top share squared, a LOWER BOUND  (basis "top_share_only")
     because the rest is unknown and treated as fully fragmented
  3. nothing supplied -> 0                                                    (basis "none")
"""

UNCONCENTRATED_BELOW = 1500
HIGHLY_CONCENTRATED_ABOVE = 2500
SHARE_SUM_TOLERANCE = 1e-6


def validate_shares(shares):
    """Shares are percentages: each 0-100, and together at most 100."""
    for s in shares:
        if not 0 <= s <= 100:
            raise ValueError(f"share {s} is outside 0-100")
    total = sum(shares)
    if total > 100 + SHARE_SUM_TOLERANCE:
        raise ValueError(f"shares sum to {total:g}%, more than 100%")
    return shares


def hhi(shares):
    validate_shares(shares)
    return round(sum(s * s for s in shares), 1)


def hhi_band(value):
    if value > HIGHLY_CONCENTRATED_ABOVE:
        return "high"
    if value >= UNCONCENTRATED_BELOW:
        return "moderate"
    return "unconcentrated"


BAND_LABEL = {"unconcentrated": "🟢 Unconcentrated", "moderate": "🟡 Moderately concentrated",
              "high": "🔴 Highly concentrated"}
BAND_COLOR = {"unconcentrated": "GREEN", "moderate": "YELLOW", "high": "RED"}


def _concentration(shares, top_amount, total):
    if shares:
        return hhi(shares), "shares"
    if top_amount and total:
        return hhi([100 * top_amount / total]), "top_share_only"
    return 0.0, "none"


def get_dependency_score(top_platform_rev, total_revenue, top_supplier_spend, total_purchases,
                         platform_shares=None, supplier_shares=None):
    platform_ratio = (top_platform_rev / total_revenue) if total_revenue > 0 else 0
    supplier_ratio = (top_supplier_spend / total_purchases) if total_purchases > 0 else 0
    if platform_shares:
        platform_ratio = max(platform_shares) / 100
    if supplier_shares:
        supplier_ratio = max(supplier_shares) / 100

    platform_hhi, platform_basis = _concentration(platform_shares, top_platform_rev, total_revenue)
    supplier_hhi, supplier_basis = _concentration(supplier_shares, top_supplier_spend, total_purchases)
    max_hhi = max(platform_hhi, supplier_hhi)
    band = hhi_band(max_hhi)

    return {
        "platform_dependency": round(platform_ratio * 100, 1),
        "supplier_dependency": round(supplier_ratio * 100, 1),
        "platform_hhi": platform_hhi,
        "supplier_hhi": supplier_hhi,
        "platform_basis": platform_basis,
        "supplier_basis": supplier_basis,
        "max_hhi": max_hhi,
        "band": band,
        "status": BAND_LABEL[band][2:],
        "color": BAND_COLOR[band],
        "label": BAND_LABEL[band],
    }
