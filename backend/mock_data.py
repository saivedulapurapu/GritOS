import random

def generate_mock_business():
    """
    Generates a realistic mock business profile for testing/demo.
    Categories: 
    - 0: High Growth (High Revenue, High CAC, Low Profit)
    - 1: Stable/Bootstrapped (Moderate Revenue, Low CAC, High Profit)
    - 2: Fragile (Low Revenue, High Fixed Costs, Low Cash)
    """
    biz_type = random.choice(["growth", "stable", "fragile"])
    
    if biz_type == "growth":
        revenue = random.randint(1500000, 3000000)
        ad_spend = revenue * random.uniform(0.35, 0.5)
        cogs = revenue * random.uniform(0.2, 0.3)
        shipping = revenue * 0.05
        rto_cost = revenue * 0.03
        fixed_costs = random.randint(300000, 500000)
        cash = random.randint(1000000, 2000000)
    elif biz_type == "stable":
        revenue = random.randint(800000, 1500000)
        ad_spend = revenue * random.uniform(0.1, 0.2)
        cogs = revenue * random.uniform(0.3, 0.4)
        shipping = revenue * 0.05
        rto_cost = revenue * 0.01
        fixed_costs = random.randint(100000, 200000)
        cash = random.randint(2000000, 5000000)
    else: # fragile
        revenue = random.randint(300000, 600000)
        ad_spend = revenue * random.uniform(0.4, 0.6)
        cogs = revenue * random.uniform(0.4, 0.5)
        shipping = revenue * 0.08
        rto_cost = revenue * 0.1
        fixed_costs = random.randint(150000, 250000)
        cash = random.randint(50000, 200000)

    return {
        "revenue": round(revenue, 2),
        "ad_spend": round(ad_spend, 2),
        "cogs": round(cogs, 2),
        "shipping_cost": round(shipping, 2),
        "rto_cost": round(rto_cost, 2),
        "fixed_costs": round(fixed_costs, 2),
        "cash_in_bank": round(cash, 2),
        "top_platform_rev": round(revenue * random.uniform(0.4, 0.9), 2),
        "stock_units": random.randint(1000, 10000),
        "cost_per_unit": random.randint(100, 1000),
        "daily_velocity": random.randint(5, 100),
        "top_supplier_spend": round((revenue * 0.4) * random.uniform(0.5, 0.9), 2),
        "total_purchases": round(revenue * 0.4, 2)
    }
