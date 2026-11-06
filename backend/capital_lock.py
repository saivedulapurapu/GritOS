def calculate_capital_lock(units_in_stock, cost_per_unit, daily_sales_velocity, currency_symbol="₹"):
    """
    Component 3: Capital Lock Index
    Measures how much money is stuck in inventory and warns if flexibility is low.
    Days to sell through = units / daily velocity. None = stock held but no sales
    velocity, so it never sells through. No stock at all is 0 days (nothing locked).
    """
    inventory_value = units_in_stock * cost_per_unit

    if units_in_stock == 0:
        days_to_liquidate = 0.0
    elif daily_sales_velocity > 0:
        days_to_liquidate = units_in_stock / daily_sales_velocity
    else:
        days_to_liquidate = None

    risk_level = "GREEN"
    if days_to_liquidate is None or days_to_liquidate > 60:
        risk_level = "RED"
        warning = f"{currency_symbol}{inventory_value:,} is trapped and cannot be reinvested. Your stock turnover is dangerously slow."
    elif days_to_liquidate > 30:
        risk_level = "YELLOW"
        warning = f"{currency_symbol}{inventory_value:,} is locked in inventory. Monitor sales velocity closely."
    elif units_in_stock == 0:
        warning = "No stock held."
    else:
        warning = "Inventory liquidity is healthy."

    return {
        "locked_capital": inventory_value,
        "days_to_liquidate": round(days_to_liquidate, 1) if days_to_liquidate is not None else None,
        "risk_level": risk_level,
        "warning": warning
    }
