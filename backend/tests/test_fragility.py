"""Fix 2: rule-based fragility tiers (replaces the 7-row RandomForest)."""
import pytest

from fragility_model import TIERS, classify_fragility

tier = lambda *a: classify_fragility(*a)["class"]


# ---------- tier table invariants ----------

def test_runway_factors_never_extend_runway():
    assert all(t["runway_factor"] <= 1.0 for t in TIERS.values())


def test_runway_factors_documented_values():
    assert TIERS["Critical"]["runway_factor"] == 0.6
    assert TIERS["Fragile"]["runway_factor"] == 0.8
    assert TIERS["Stable"]["runway_factor"] == 1.0
    assert TIERS["Resilient"]["runway_factor"] == 1.0


def test_scores_increase_with_health():
    s = [TIERS[t]["score"] for t in ("Critical", "Fragile", "Stable", "Resilient")]
    assert s == sorted(s) and len(set(s)) == 4


# ---------- Critical ----------

def test_audit_loss_maker_is_critical():
    # margin 23%, runway 1.35 months (old RandomForest said "Anti-Fragile")
    r = classify_fragility(23.0, 1.35, 0.3)
    assert r["class"] == "Critical"
    assert "Runway under 3 months" in r["reasons"]


def test_zero_runway_is_critical():
    assert tier(23.0, 0.0, 0.3) == "Critical"


def test_negative_margin_is_critical_even_without_burn():
    r = classify_fragility(-5.0, None, 0.2)
    assert r["class"] == "Critical"
    assert any("margin" in reason for reason in r["reasons"])


@pytest.mark.parametrize("runway, expected", [(2.99, "Critical"), (3.0, "Fragile")])
def test_critical_runway_boundary(runway, expected):
    # 3 months is the line: strictly under 3 is Critical
    assert tier(25.0, runway, 0.2) == expected


# ---------- Fragile ----------

@pytest.mark.parametrize(
    "margin, runway, ad_ratio, expected",
    [
        (25.0, 5.99, 0.2, "Fragile"),   # runway under 6
        (25.0, 6.0, 0.2, "Stable"),     # 6 is not under 6; under 12 -> Stable
        (9.99, None, 0.2, "Fragile"),   # margin under 10%
        (10.0, None, 0.2, "Stable"),    # 10% is not under 10%; under 20% -> Stable
        (25.0, None, 0.51, "Fragile"),  # ad spend over 50% of revenue
        (25.0, None, 0.5, "Stable"),    # exactly 50% is not over; over 30% -> Stable
    ],
)
def test_fragile_boundaries(margin, runway, ad_ratio, expected):
    assert tier(margin, runway, ad_ratio) == expected


def test_fragile_lists_every_trigger():
    r = classify_fragility(5.0, 4.0, 0.6)
    assert r["class"] == "Fragile"
    assert len(r["reasons"]) == 3


# ---------- Stable / Resilient ----------

def test_frontend_default_is_resilient():
    # margin 23%, no burn, ad ratio 0.3 (exactly at the limit, not over)
    r = classify_fragility(23.0, None, 0.3)
    assert r["class"] == "Resilient"
    assert r["score"] == 100


@pytest.mark.parametrize("runway, expected", [(11.99, "Stable"), (12.0, "Resilient")])
def test_resilient_runway_boundary(runway, expected):
    assert tier(25.0, runway, 0.2) == expected


def test_stable_explains_what_blocks_resilient():
    r = classify_fragility(15.0, None, 0.35)
    assert r["class"] == "Stable"
    assert r["reasons"] == ["Contribution margin under 20%", "Ad spend over 30% of revenue"]


def test_result_shape():
    r = classify_fragility(23.0, None, 0.3)
    assert set(r) == {"class", "color", "score", "runway_factor", "reasons"}
