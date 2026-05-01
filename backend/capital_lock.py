def calculate_capital_lock(units_in_stock, cost_per_unit, daily_sales_velocity):
    """
    Component 3: Capital Lock Index
    Measures how much money is stuck in inventory and warns if flexibility is low.
    """
    inventory_value = units_in_stock * cost_per_unit
    
    # Capital Lock Risk: Calculated by turnover vs stock
    # If turnover is slow/velocity is low, warned that cash is trapped.
    # Logic: If inventory lasts more than 30 days, it's 'trapped'.
    days_to_liquidate = (units_in_stock / daily_sales_velocity) if daily_sales_velocity > 0 else 999
    
    risk_level = "GREEN"
    if days_to_liquidate > 60: 
        risk_level = "RED"
        warning = f"₹{inventory_value:,} is trapped and cannot be reinvested. Your stock turnover is dangerously slow."
    elif days_to_liquidate > 30: 
        risk_level = "YELLOW"
        warning = f"₹{inventory_value:,} is locked in inventory. Monitor sales velocity closely."
    else:
        warning = "Inventory liquidity is healthy."

    return {
        "locked_capital": inventory_value,
        "days_to_liquidate": round(days_to_liquidate, 1),
        "risk_level": risk_level,
        "warning": warning
    }
