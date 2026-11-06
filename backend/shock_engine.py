import financial_engine

AD_SPEND_BEHAVIOURS = ("fixed", "scales")


def apply_shocks(baseline_data, kak_inc_pct, revenue_drop_pct, cogs_inc_pct, ad_spend_behaviour="fixed"):
    """
    Recalculates metrics under a stress scenario.

    ad_spend_behaviour: what ad spend does when revenue falls.
      "fixed"  (default): the ad budget does not flex with demand in the short
               term (committed campaigns, agency retainers, minimum spends), so
               a revenue drop raises effective CAC instead of cutting spend.
               This is the cautious assumption for a stress test.
      "scales": ad spend falls in proportion to volume (CAC per order unchanged).
    The ad-cost shock (kak_inc_pct) raises ad spend in both modes.
    """
    if ad_spend_behaviour not in AD_SPEND_BEHAVIOURS:
        raise ValueError(f"ad_spend_behaviour must be one of {AD_SPEND_BEHAVIOURS}, got {ad_spend_behaviour!r}")

    # Baseline inputs
    rev = baseline_data.get('revenue', 0)
    cac = baseline_data.get('ad_spend', 0)
    cogs = baseline_data.get('cogs', 0)
    shipping = baseline_data.get('shipping_cost', 0)
    rto = baseline_data.get('rto_cost', 0)
    fixed = baseline_data.get('fixed_costs', 0)
    cash = baseline_data.get('cash_in_bank', 0)

    # Apply shock multipliers to variables tracking volume
    vol = max(0, 1 - (revenue_drop_pct / 100))
    new_rev = rev * vol
    
    # Ad spend follows volume only in "scales" mode; the CAC shock raises it either way
    ad_volume = vol if ad_spend_behaviour == "scales" else 1.0
    new_cac = cac * ad_volume * (1 + (kak_inc_pct / 100))
    # COGS drops with volume, but price per unit increases per shock
    new_cogs = cogs * vol * (1 + (cogs_inc_pct / 100))
    
    # Other variable costs scale proportionally to volume 
    new_shipping = shipping * vol
    new_rto = rto * vol

    # Recalculate using central engine for consistency
    metrics = financial_engine.calculate_operational_metrics(new_rev, new_cac, new_cogs, new_shipping, new_rto)
    bottom_line = financial_engine.calculate_net_metrics(metrics['contribution_margin'], fixed, cash)
    
    return {
        "rev": round(new_rev, 2),
        "net_profit": bottom_line['net_profit'],
        "runway": bottom_line['runway_months'],  # None = no cash burn
        # Inputs for the stressed fragility tier
        "margin_percent": metrics['margin_percent'],
        "ad_spend_ratio": (new_cac / new_rev) if new_rev > 0 else 0,
    }
