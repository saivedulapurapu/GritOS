import copy

import pytest

from shock_engine import apply_shocks

money = lambda x: pytest.approx(x, abs=0.01)

# Frontend default business (BusinessContext.js).
# Unshocked: contribution = 1,000,000 - 300,000 - 400,000 - 50,000 - 20,000 = 230,000
#            net = 230,000 - 150,000 = +80,000 (profitable)
BASE = {
    "revenue": 1_000_000,
    "ad_spend": 300_000,
    "cogs": 400_000,
    "shipping_cost": 50_000,
    "rto_cost": 20_000,
    "fixed_costs": 150_000,
    "cash_in_bank": 500_000,
}


def test_no_shock_reproduces_baseline():
    # No shocks -> same as baseline: rev 1,000,000, net +80,000
    # Profitable -> no cash burn -> runway None (standardised sentinel, Fix 1)
    r = apply_shocks(BASE, 0, 0, 0)
    assert r["rev"] == money(1_000_000)
    assert r["net_profit"] == money(80_000)
    assert r["net_profit"] > 0
    assert r["runway"] is None


def test_revenue_drop_scales_costs_with_volume_ASSUMPTION():
    # MODEL ASSUMPTION: ad spend scales with volume. Debatable — in reality ad spend
    #  is often fixed short-term, so CAC rises when demand falls. Revisit in Fix 2.
    # vol = 1 - 0.50 = 0.5
    # rev 500,000 | ads 150,000 | COGS 200,000 | ship 25,000 | RTO 10,000
    # contribution = 500,000 - 385,000 = 115,000; fixed costs do NOT scale
    # net = 115,000 - 150,000 = -35,000  ->  runway = 500,000 / 35,000 = 14.2857 -> 14.29
    r = apply_shocks(BASE, 0, 50, 0)
    assert r["rev"] == money(500_000)
    assert r["net_profit"] == money(-35_000)
    assert r["runway"] == money(14.29)


def test_ad_cost_shock_only_raises_ad_spend():
    # ads = 300,000 * (1 + 1.00) = 600,000; everything else unchanged
    # contribution = 1,000,000 - 600,000 - 400,000 - 50,000 - 20,000 = -70,000
    # net = -70,000 - 150,000 = -220,000  ->  runway = 500,000 / 220,000 = 2.2727 -> 2.27
    r = apply_shocks(BASE, 100, 0, 0)
    assert r["rev"] == money(1_000_000)
    assert r["net_profit"] == money(-220_000)
    assert r["runway"] == money(2.27)


def test_cogs_shock_only_raises_cogs():
    # COGS = 400,000 * 1.50 = 600,000
    # contribution = 1,000,000 - 300,000 - 600,000 - 50,000 - 20,000 = 30,000
    # net = 30,000 - 150,000 = -120,000  ->  runway = 500,000 / 120,000 = 4.1667 -> 4.17
    r = apply_shocks(BASE, 0, 0, 50)
    assert r["net_profit"] == money(-120_000)
    assert r["runway"] == money(4.17)


def test_combined_shocks_compound():
    # vol = 0.8
    # rev 800,000 | ads 300,000*0.8*1.5 = 360,000 | COGS 400,000*0.8*1.25 = 400,000
    # ship 40,000 | RTO 16,000
    # contribution = 800,000 - 816,000 = -16,000; net = -16,000 - 150,000 = -166,000
    # runway = 500,000 / 166,000 = 3.0120 -> 3.01
    r = apply_shocks(BASE, 50, 20, 25)
    assert r["rev"] == money(800_000)
    assert r["net_profit"] == money(-166_000)
    assert r["runway"] == money(3.01)


def test_total_revenue_loss_leaves_only_fixed_costs():
    # vol = 0 -> all revenue and variable costs are 0; net = -150,000 (fixed costs)
    # runway = 500,000 / 150,000 = 3.333 -> 3.33
    r = apply_shocks(BASE, 0, 100, 0)
    assert r["rev"] == money(0)
    assert r["net_profit"] == money(-150_000)
    assert r["runway"] == money(3.33)


def test_revenue_drop_over_100_clamps_volume_at_zero():
    # vol = max(0, 1 - 1.5) = 0 -> identical to a 100% drop, never negative revenue
    assert apply_shocks(BASE, 0, 150, 0) == apply_shocks(BASE, 0, 100, 0)


def test_does_not_mutate_input():
    original = copy.deepcopy(BASE)
    apply_shocks(BASE, 50, 50, 50)
    assert BASE == original
