import numpy as np
from sklearn.ensemble import RandomForestClassifier

from financial_engine import runway_as_number

# Simulated training data for supervised learning
# Features: [Margin%, RunwayMonths, AdSpendRatio]
# Classes: 0: Anti-Fragile, 1: Sensitive, 2: Critical
X_train = np.array([
    [25, 12, 0.2],  # Anti-Fragile
    [30, 24, 0.1],  # Anti-Fragile
    [10, 4, 0.5],   # Sensitive
    [12, 5, 0.4],   # Sensitive
    [2, 1, 0.8],    # Critical
    [4, 0.5, 0.9],  # Critical
    [40, 36, 0.05], # Anti-Fragile
])
y_train = np.array([0, 0, 1, 1, 2, 2, 0])

# Initialize and Train
clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

def classify_fragility(margin_pct, burn_rate, runway, ad_spend_ratio=0.2):
    """
    Component 6: Fragility Scoring Layer (ML Classification)
    Classifies business health into Anti-Fragile, Sensitive, or Critical.
    """
    runway_val = runway_as_number(runway)

    features = np.array([[margin_pct, runway_val, ad_spend_ratio]])
    probs = clf.predict_proba(features)[0]
    class_idx = np.argmax(probs)
    
    mapping = {
        0: {"class": "Anti-Fragile", "color": "GREEN", "score": 100},
        1: {"class": "Sensitive", "color": "YELLOW", "score": 50},
        2: {"class": "Critical", "color": "RED", "score": 20}
    }
    
    result = mapping[class_idx]
    result['confidence'] = round(float(np.max(probs)) * 100, 1)
    return result

# Runway beyond this horizon counts as "safe". Capping both runways here puts an
# infinite (None) runway on the same scale as a long finite one.
SENSITIVITY_HORIZON_MONTHS = 12.0


def get_shock_sensitivity(baseline_runway, shock_runway, total_shock_pct):
    """
    Component 7: Shock Sensitivity Score
    Formula: months of runway lost / total shock, where total shock is the sum of
    the revenue-drop, ad-cost and COGS shock percentages.
    Runways (None = no cash burn) are capped at SENSITIVITY_HORIZON_MONTHS.
    A shock that lengthens runway scores 0, never negative.
    """
    if total_shock_pct <= 0:
        return 0

    horizon = SENSITIVITY_HORIZON_MONTHS
    b_val = horizon if baseline_runway is None else min(float(baseline_runway), horizon)
    s_val = horizon if shock_runway is None else min(float(shock_runway), horizon)

    runway_lost = max(0.0, b_val - s_val)
    return round(runway_lost / total_shock_pct, 3)
