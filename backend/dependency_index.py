def get_dependency_score(top_platform_rev, total_revenue, top_supplier_spend, total_purchases):
    """
    Component 4: Platform & Supplier Dependency Index
    Measures concentration risk for both sales and supply chain.
    """
    # Platform Dependency
    platform_ratio = (top_platform_rev / total_revenue) if total_revenue > 0 else 0
    
    # Supplier Dependency
    supplier_ratio = (top_supplier_spend / total_purchases) if total_purchases > 0 else 0
    
    # Aggregate Risk Level
    max_ratio = max(platform_ratio, supplier_ratio)
    
    if max_ratio > 0.7:
        status = "High Dependency"
        color = "RED"
        label = "🔴 High Dependency"
    elif max_ratio > 0.4:
        status = "Moderate Risk"
        color = "YELLOW"
        label = "🟡 Moderate Risk"
    else:
        status = "Diversified"
        color = "GREEN"
        label = "🟢 Diversified"
        
    return {
        "platform_dependency": round(platform_ratio * 100, 1),
        "supplier_dependency": round(supplier_ratio * 100, 1),
        "status": status,
        "color": color,
        "label": label
    }
