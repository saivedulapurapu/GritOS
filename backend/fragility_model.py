import numpy as np
from sklearn.ensemble import RandomForestClassifier

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
    try:
        runway_val = 999.0 if runway == "Infinite" else float(runway)
    except:
        runway_val = 0.0

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

def get_shock_sensitivity(baseline_runway, shock_runway, shock_percent):
    """
    Component 7: Shock Sensitivity Score
    Formula: Change in runway / Shock %
    Measures how much business stability degrades under stress.
    """
    if shock_percent == 0:
        return 0
        
    try:
        b_val = 999.0 if baseline_runway == "Infinite" else float(baseline_runway)
        s_val = 999.0 if shock_runway == "Infinite" else float(shock_runway)
    except:
        return 0
        
    runway_delta = abs(b_val - s_val)
    # Avoid division by zero and handle infinity
    if runway_delta > 900: # One was infinite, other likely wasn't
        runway_delta = 12 # Cap delta at 1 year for sensitivity calc
        
    sensitivity = runway_delta / shock_percent
    return round(sensitivity, 2)
