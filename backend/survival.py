import math

def calculate_survival_probability(runway_months, fragility_class, shock_sensitivity):
    """
    Component 5: Survival Analysis for D2C
    Predicts probability of business becoming bankrupt/failing within 6 months.
    """
    try:
        runway_val = 999.0 if runway_months == "Infinite" else float(runway_months)
    except:
        runway_val = 0.0

    # Base survival horizon: 6 months
    t = 6 
    
    # Lambda (Expected survival time) is grounded in runway
    lambd = runway_val
    
    # Adjust lambda based on fragility classification
    if fragility_class == "Critical":
        lambd *= 0.4
    elif fragility_class == "Sensitive":
        lambd *= 0.8
    elif fragility_class == "Anti-Fragile":
        lambd *= 2.5
        
    # Subtract risk based on sensitivity
    lambd = max(0.1, lambd - (shock_sensitivity * 0.1))
    
    # P(Solvent) = e^(-t/lambda)
    prob = math.exp(-t / lambd) * 100
    
    # Clip to realistic bounds
    if runway_val > 12 and fragility_class == "Anti-Fragile":
        return 99.9
        
    return round(min(99.9, prob), 1)

def calculate_survival_trajectory(runway_months, fragility_class, shock_sensitivity):
    """
    Computes genuine mathematical trajectory over 6 months using exponential decay.
    """
    try:
        runway_val = 999.0 if runway_months == "Infinite" else float(runway_months)
    except:
        runway_val = 0.0

    lambd = runway_val
    if fragility_class == "Critical":
        lambd *= 0.4
    elif fragility_class == "Sensitive":
        lambd *= 0.8
    elif fragility_class == "Anti-Fragile":
        lambd *= 2.5
        
    lambd = max(0.1, lambd - (shock_sensitivity * 0.1))

    trajectory = []
    for t in range(1, 7):
        prob = math.exp(-t / lambd) * 100
        if runway_val > 12 and fragility_class == "Anti-Fragile":
            prob = 99.9
        trajectory.append({
            "name": f"Month {t}",
            "prob": round(min(99.9, prob), 1)
        })
        
    return trajectory
