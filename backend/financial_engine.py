def calculate_operational_metrics(revenue, ad_spend, cogs, shipping, rto_cost=0):
    """
    Computes real profitability before fixed costs.
    Formula: Revenue - Ad Spend - COGS - Shipping - RTO
    """
    contribution_margin = revenue - ad_spend - cogs - shipping - rto_cost
    margin_percent = (contribution_margin / revenue * 100) if revenue > 0 else 0
    return {
        "contribution_margin": round(contribution_margin, 2),
        "margin_percent": round(margin_percent, 2)
    }

def calculate_net_metrics(contribution_margin, fixed_costs, cash):
    """
    Computes bottom-line results, burn rate, and runway.
    """
    net_profit = contribution_margin - fixed_costs
    is_profitable = net_profit >= 0
    
    burn_rate = abs(net_profit) if not is_profitable else 0
    runway = (cash / burn_rate) if burn_rate > 0 else float('inf')
    
    return {
        "net_profit": round(net_profit, 2),
        "burn_rate": round(burn_rate, 2),
        "runway_months": round(runway, 2) if runway != float('inf') else "Infinite",
        "is_profitable": is_profitable
    }
