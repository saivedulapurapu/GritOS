import pytest

from financial_engine import calculate_operational_metrics, calculate_net_metrics

money = lambda x: pytest.approx(x, abs=0.01)


# ---------- calculate_operational_metrics ----------

def test_contribution_margin_frontend_defaults():
    # 1,000,000 - 300,000 (ads) - 400,000 (COGS) - 50,000 (ship) - 20,000 (RTO) = 230,000
    # margin % = 230,000 / 1,000,000 * 100 = 23.0
    r = calculate_operational_metrics(1_000_000, 300_000, 400_000, 50_000, 20_000)
    assert r["contribution_margin"] == money(230_000)
    assert r["margin_percent"] == money(23.0)


def test_rto_defaults_to_zero():
    # 100,000 - 20,000 - 30,000 - 10,000 - 0 = 40,000  ->  40,000 / 100,000 = 40.0%
    r = calculate_operational_metrics(100_000, 20_000, 30_000, 10_000)
    assert r["contribution_margin"] == money(40_000)
    assert r["margin_percent"] == money(40.0)


def test_negative_contribution_margin():
    # 100,000 - 60,000 - 50,000 - 10,000 - 5,000 = -25,000  ->  -25,000 / 100,000 = -25.0%
    r = calculate_operational_metrics(100_000, 60_000, 50_000, 10_000, 5_000)
    assert r["contribution_margin"] == money(-25_000)
    assert r["margin_percent"] == money(-25.0)


def test_zero_revenue_margin_percent_guarded():
    # 0 - 1,000 = -1,000; margin % would be -1,000 / 0 -> guarded to 0, no ZeroDivisionError
    r = calculate_operational_metrics(0, 1_000, 0, 0, 0)
    assert r["contribution_margin"] == money(-1_000)
    assert r["margin_percent"] == 0


def test_margin_percent_rounded_to_two_dp():
    # 3 - 1 = 2  ->  2 / 3 * 100 = 66.666...  ->  66.67
    r = calculate_operational_metrics(3, 1, 0, 0, 0)
    assert r["margin_percent"] == 66.67


# ---------- calculate_net_metrics ----------

def test_profitable_business_has_no_burn_and_infinite_runway():
    # net = 230,000 - 150,000 = 80,000 (profit)  ->  burn 0  ->  runway "Infinite"
    r = calculate_net_metrics(230_000, 150_000, 500_000)
    assert r["net_profit"] == money(80_000)
    assert r["burn_rate"] == 0
    assert r["runway_months"] == "Infinite"
    assert r["is_profitable"] is True


def test_breakeven_counts_as_profitable():
    # net = 150,000 - 150,000 = 0  ->  is_profitable (>= 0), burn 0, runway "Infinite"
    r = calculate_net_metrics(150_000, 150_000, 500_000)
    assert r["net_profit"] == money(0)
    assert r["burn_rate"] == 0
    assert r["runway_months"] == "Infinite"
    assert r["is_profitable"] is True


def test_loss_making_burn_and_runway():
    # net = 230,000 - 600,000 = -370,000  ->  burn 370,000
    # runway = 500,000 / 370,000 = 1.35135...  ->  1.35 months
    r = calculate_net_metrics(230_000, 600_000, 500_000)
    assert r["net_profit"] == money(-370_000)
    assert r["burn_rate"] == money(370_000)
    assert r["runway_months"] == money(1.35)
    assert r["is_profitable"] is False


def test_loss_making_with_zero_cash_has_zero_runway():
    # burn 370,000, cash 0  ->  runway = 0 / 370,000 = 0.0
    r = calculate_net_metrics(230_000, 600_000, 0)
    assert r["runway_months"] == money(0.0)


def test_negative_contribution_adds_to_burn():
    # net = -25,000 - 50,000 = -75,000  ->  burn 75,000
    # runway = 300,000 / 75,000 = 4.0 months
    r = calculate_net_metrics(-25_000, 50_000, 300_000)
    assert r["net_profit"] == money(-75_000)
    assert r["burn_rate"] == money(75_000)
    assert r["runway_months"] == money(4.0)
