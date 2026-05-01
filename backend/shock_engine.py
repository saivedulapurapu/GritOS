import financial_engine

def apply_shocks(baseline_data, kak_inc_pct, revenue_drop_pct, cogs_inc_pct):
    """
    Recalculates metrics based on interactive slider inputs.
    """
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
    
    # CAC and COGS drop with volume, but price per unit increases per shock 
    new_cac = cac * vol * (1 + (kak_inc_pct / 100))
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
        "runway": bottom_line['runway_months'] if bottom_line['runway_months'] != "Infinite" else 999
    }
