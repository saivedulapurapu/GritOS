"""Fix 5: every EDGAR normalisation rule, on small hand-built companyfacts (no network)."""
import json
from datetime import date

import pytest

from etl import edgar_ingest as ei
from etl.edgar_ingest import Fact, NormalisationLog


def row(start, end, val, form="10-Q", filed="2024-05-01", accn="A1"):
    r = {"end": end, "val": val, "form": form, "filed": filed, "accn": accn}
    if start:
        r["start"] = start
    return r


def companyfacts(tags, name="Test Co", unit="USD"):
    return {"cik": 1, "entityName": name,
            "facts": {"us-gaap": {t: {"units": {unit: rows}} for t, rows in tags.items()}}}


def fact(start, end, val, concept="revenue", tag="Revenues", form="10-Q", filed="2024-05-01", accn="A1"):
    return Fact(concept, tag, date.fromisoformat(start) if start else None, date.fromisoformat(end), float(val),
                form, date.fromisoformat(filed), accn)


# ---------- extraction ----------

def test_extract_keeps_usd_and_counts_other_units():
    cf = {"facts": {"us-gaap": {"Revenues": {"units": {
        "USD": [row("2024-01-01", "2024-03-31", 100)],
        "shares": [row("2024-01-01", "2024-03-31", 5)],
    }}}}}
    log = NormalisationLog()
    facts = ei.extract_tag_facts(cf, "revenue", "Revenues", log)
    assert [f.value for f in facts] == [100.0]
    assert log.facts_ingested == 2 and log.dropped_other_units == 1


def test_extract_missing_tag_is_empty():
    assert ei.extract_tag_facts(companyfacts({}), "revenue", "Revenues", NormalisationLog()) == []


# ---------- form filter ----------

def test_form_filter_keeps_10k_10q_and_amendments_only():
    facts = [fact(None, "2024-03-31", 1, form=f) for f in ("10-K", "10-Q", "10-K/A", "10-Q/A", "DEF 14A", "8-K", "S-1")]
    log = NormalisationLog()
    kept = ei.filter_forms(facts, log)
    assert sorted(f.form for f in kept) == ["10-K", "10-K/A", "10-Q", "10-Q/A"]
    assert dict(log.dropped_forms) == {"DEF 14A": 1, "8-K": 1, "S-1": 1}


# ---------- restatements ----------

def test_same_value_in_several_filings_is_a_duplicate_not_a_restatement():
    log = NormalisationLog()
    out = ei.resolve_restatements([fact("2024-01-01", "2024-03-31", 100, filed="2024-05-01", accn="A"),
                                   fact("2024-01-01", "2024-03-31", 100, filed="2025-05-01", accn="B")], log)
    assert len(out) == 1 and log.duplicates_collapsed == 1 and log.restatements == []


def test_latest_filed_value_wins_and_original_is_recorded():
    # 100 (filed 2024) restated to 90 (filed 2025): 10 % change -> kind "restatement"
    log = NormalisationLog()
    out = ei.resolve_restatements([fact("2024-01-01", "2024-03-31", 90, filed="2025-05-01", accn="B"),
                                   fact("2024-01-01", "2024-03-31", 100, filed="2024-05-01", accn="A")], log)
    assert [f.value for f in out] == [90.0]
    r = log.restatements[0]
    assert (r["original_value"], r["restated_value"]) == (100.0, 90.0)
    assert (r["original_accn"], r["restated_accn"]) == ("A", "B")
    assert r["kind"] == "restatement"


@pytest.mark.parametrize(
    "original, restated, kind",
    [
        (1_262_300_000, 1_262_200_000, "rounding"),        # 0.008 % (Peloton revenue, real case)
        (100, 90, "restatement"),                           # 10 %
        (-28_639, -5_191_000, "scale_or_entity"),           # 181x (Hims 2020 shell vs operating company)
        (0, 5, "scale_or_entity"),
    ],
)
def test_restatement_kind(original, restated, kind):
    assert ei.restatement_kind(original, restated) == kind


def test_several_superseded_values_each_recorded_once():
    log = NormalisationLog()
    ei.resolve_restatements([fact("2024-01-01", "2024-03-31", v, filed=f, accn=a) for v, f, a in
                             [(100, "2024-05-01", "A"), (95, "2024-08-01", "B"), (100, "2024-09-01", "C"),
                              (90, "2025-05-01", "D")]], log)
    # 100 and 95 superseded by 90; the repeated 100 is a duplicate
    assert sorted(r["original_value"] for r in log.restatements) == [95.0, 100.0]
    assert log.duplicates_collapsed == 1


# ---------- pre-listing shell filings (SPAC / reverse merger) ----------

def test_facts_filed_before_first_revenue_filing_are_dropped():
    log = NormalisationLog()
    facts = [fact(None, "2020-03-31", 1.48e6, concept="cash", filed="2020-05-14"),   # shell's 10-Q
             fact(None, "2020-03-31", 55.2e6, concept="cash", filed="2021-05-17")]   # operating company
    kept = ei.drop_pre_first_revenue_filings(facts, date(2021, 5, 17), log)
    assert [f.value for f in kept] == [55.2e6]
    assert log.dropped_pre_first_revenue_filing == 1


def test_shell_filter_is_noop_without_revenue():
    facts = [fact(None, "2020-03-31", 1)]
    assert ei.drop_pre_first_revenue_filings(facts, None, NormalisationLog()) == facts


# ---------- tag fallback ----------

def test_tag_priority_per_period_with_fallback():
    # Primary tag reports Q2 only; fallback fills Q1; both report Q3 -> primary wins
    by_tag = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": [fact("2024-04-01", "2024-06-30", 20), fact("2024-07-01", "2024-09-30", 30)],
        "Revenues": [fact("2024-01-01", "2024-03-31", 10, tag="Revenues"), fact("2024-07-01", "2024-09-30", 999, tag="Revenues")],
    }
    for f in by_tag["RevenueFromContractWithCustomerExcludingAssessedTax"]:
        f.tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    log = NormalisationLog()
    chosen = {f.end.month: f for f in ei.select_tags(by_tag, ei.CONCEPTS["revenue"][1], "revenue", log)}
    assert chosen[3].tag == "Revenues" and chosen[3].value == 10
    assert chosen[9].value == 30
    assert log.tag_variants["revenue"] == {"RevenueFromContractWithCustomerExcludingAssessedTax": 2, "Revenues": 1}


# ---------- duration classes and quarter keys ----------

@pytest.mark.parametrize(
    "start, end, cls",
    [("2024-01-01", "2024-03-31", "Q"), ("2024-01-01", "2024-06-30", "H1"), ("2024-01-01", "2024-09-30", "9M"),
     ("2024-01-01", "2024-12-31", "FY"), ("2024-01-01", "2024-02-29", "other"), (None, "2024-03-31", "instant"),
     ("2024-02-05", "2025-02-02", "FY")],  # 52-week year
)
def test_duration_class(start, end, cls):
    assert ei.duration_class(fact(start, end, 1)) == cls


@pytest.mark.parametrize(
    "end, key",
    [("2025-03-31", "2025-Q1"), ("2025-06-30", "2025-Q2"), ("2025-09-30", "2025-Q3"), ("2025-12-31", "2025-Q4"),
     ("2025-02-02", "2025-Q1"),   # Lovesac fiscal Q4 (Nov-Jan) ends 2 Feb: labelled by end date -> 2025-Q1
     ("2025-05-04", "2025-Q2"),   # 52/53-week quarter ending 4 May
     ("2025-01-10", "2024-Q4")],  # ends 10 Jan: mostly the previous calendar quarter
)
def test_quarter_key_by_period_end(end, key):
    assert ei.quarter_key(date.fromisoformat(end)) == key


# ---------- quarterisation: Q4 and YTD ----------

def test_q4_derived_from_fy_minus_three_quarters():
    # Q1 100 + Q2 110 + Q3 120 = 330; FY 480 -> Q4 = 150
    facts = [fact("2024-01-01", "2024-03-31", 100), fact("2024-04-01", "2024-06-30", 110),
             fact("2024-07-01", "2024-09-30", 120), fact("2024-01-01", "2024-12-31", 480, form="10-K")]
    log = NormalisationLog()
    out = ei.quarterize_flow(facts, log)
    q4 = out[date(2024, 12, 31)]
    assert q4.value == 150 and q4.provenance == "DERIVED" and q4.method == "q4_from_fy"
    assert q4.start == date(2024, 10, 1)
    assert log.q4_derived == 1 and log.ytd_conversions == 0
    assert all(out[d].method == "reported" for d in (date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30)))


def test_ytd_cash_flow_converted_to_quarters_by_differencing():
    # Cash flow is only reported year-to-date: 3M -10, 6M -25, 9M -30, FY -20
    # Q1 = -10 (reported), Q2 = -25 - (-10) = -15, Q3 = -30 - (-25) = -5, Q4 = -20 - (-10 - 15 - 5) = 10
    facts = [fact("2024-01-01", e, v, concept="operating_cash_flow", tag="NetCashProvidedByUsedInOperatingActivities")
             for e, v in (("2024-03-31", -10), ("2024-06-30", -25), ("2024-09-30", -30), ("2024-12-31", -20))]
    log = NormalisationLog()
    out = ei.quarterize_flow(facts, log)
    assert [out[date(2024, m, d)].value for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))] == [-10, -15, -5, 10]
    assert [out[date(2024, m, d)].method for m, d in ((6, 30), (9, 30), (12, 31))] == ["ytd_difference", "ytd_difference", "q4_from_fy"]
    assert log.ytd_conversions == 2 and log.q4_derived == 1


def test_q3_from_9m_minus_reported_q1_q2_when_h1_missing():
    # Q1 10, Q2 20 reported; 9M 45 -> Q3 = 45 - 30 = 15
    facts = [fact("2024-01-01", "2024-03-31", 10), fact("2024-04-01", "2024-06-30", 20),
             fact("2024-01-01", "2024-09-30", 45)]
    out = ei.quarterize_flow(facts, NormalisationLog())
    assert out[date(2024, 9, 30)].value == 15 and out[date(2024, 9, 30)].method == "ytd_difference"


def test_q4_from_fy_minus_9m_when_quarters_incomplete():
    # Only 9M (60) and FY (100) reported -> Q4 = 40 (Q1-Q3 individually unknown)
    facts = [fact("2024-01-01", "2024-09-30", 60), fact("2024-01-01", "2024-12-31", 100, form="10-K")]
    out = ei.quarterize_flow(facts, NormalisationLog())
    assert out[date(2024, 12, 31)].value == 40 and out[date(2024, 12, 31)].method == "q4_from_fy_minus_9m"


def test_reported_quarter_is_never_overwritten_by_derivation():
    # Q4 reported directly as 151 although FY - Q1..Q3 = 150
    facts = [fact("2024-01-01", "2024-03-31", 100), fact("2024-04-01", "2024-06-30", 110),
             fact("2024-07-01", "2024-09-30", 120), fact("2024-10-01", "2024-12-31", 151),
             fact("2024-01-01", "2024-12-31", 480, form="10-K")]
    out = ei.quarterize_flow(facts, NormalisationLog())
    assert out[date(2024, 12, 31)].value == 151 and out[date(2024, 12, 31)].method == "reported"


def test_non_calendar_fiscal_year_aligned_by_period_end():
    # June fiscal year (like Peloton): FY Jul 2024 - Jun 2025; Q1..Q3 reported, Q4 (Apr-Jun) derived
    facts = [fact("2024-07-01", "2024-09-30", 50), fact("2024-10-01", "2024-12-31", 60),
             fact("2025-01-01", "2025-03-31", 70), fact("2024-07-01", "2025-06-30", 250, form="10-K")]
    out = ei.quarterize_flow(facts, NormalisationLog())
    q4 = out[date(2025, 6, 30)]
    assert q4.value == 70 and q4.start == date(2025, 4, 1)   # 250 - (50 + 60 + 70)
    assert ei.quarter_key(q4.end) == "2025-Q2"                # calendar quarter of the period end


def test_53_week_quarters_chain_within_tolerance():
    # 52/53-week calendar: next quarter starts the day after the previous ends
    facts = [fact("2024-02-05", "2024-05-05", 10), fact("2024-05-06", "2024-08-04", 20),
             fact("2024-08-05", "2024-11-03", 30), fact("2024-02-05", "2025-02-02", 100, form="10-K")]
    out = ei.quarterize_flow(facts, NormalisationLog())
    assert out[date(2025, 2, 2)].value == 40


def test_other_durations_ignored_and_counted():
    log = NormalisationLog()
    ei.quarterize_flow([fact("2024-01-01", "2024-02-29", 5)], log)
    assert log.dropped_other_durations == 1


# ---------- annual advertising, coverage ----------

def test_advertising_for_quarter_uses_containing_fiscal_year():
    annual = ei.annual_facts([fact("2024-01-01", "2024-12-31", 1200, concept="advertising", tag="AdvertisingExpense", form="10-K")])
    assert ei.advertising_for_quarter(annual, date(2024, 6, 30)).value == 1200
    assert ei.advertising_for_quarter(annual, date(2025, 3, 31)) is None


def test_normalise_company_and_coverage_matrix():
    cf = companyfacts({
        "Revenues": [row("2024-01-01", "2024-03-31", 300), row("2024-04-01", "2024-06-30", 330)],
        "CostOfRevenue": [row("2024-01-01", "2024-03-31", 120)],
        "MarketingExpense": [row("2024-01-01", "2024-03-31", 30)],
        "CashAndCashEquivalentsAtCarryingValue": [row(None, "2024-03-31", 1000), row(None, "2024-06-30", 900)],
    })
    company = ei.normalise_company(cf, "TST")
    assert sorted(company.quarters) == ["2024-Q1", "2024-Q2"]
    m = ei.coverage_matrix(company)
    assert m["revenue"] == {"2024-Q1": "REAL", "2024-Q2": "REAL"}
    assert m["cogs"] == {"2024-Q1": "REAL", "2024-Q2": "MISSING"}     # gap stays a gap
    assert m["advertising"] == {"2024-Q1": "PROXY", "2024-Q2": "MISSING"}
    assert m["cash"]["2024-Q2"] == "REAL"


# ---------- fetcher (fake opener, fake clock: no network) ----------

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetcher_requires_contact_user_agent():
    with pytest.raises(ValueError):
        ei.Fetcher("")
    with pytest.raises(ValueError):
        ei.Fetcher("no contact here")


def test_fetcher_sends_user_agent_and_rate_limits():
    sent, sleeps, now = [], [], [0.0]

    def opener(req, timeout):
        sent.append(req.get_header("User-agent"))
        return FakeResponse({"ok": True})

    f = ei.Fetcher("Test agent test@example.com", opener=opener, sleep=sleeps.append, clock=lambda: now[0])
    f.get_json("https://example.invalid/a")
    now[0] += 0.05                      # second call 50 ms later -> must wait 100 ms
    f.get_json("https://example.invalid/b")
    assert sent == ["Test agent test@example.com"] * 2
    assert sleeps == [pytest.approx(ei.MIN_REQUEST_INTERVAL_S - 0.05)]
    assert f.requests == 2


def test_fetch_uses_cache_and_resolves_ciks(tmp_path):
    calls = []

    def opener(req, timeout):
        calls.append(req.full_url)
        if "company_tickers" in req.full_url:
            return FakeResponse({"0": {"ticker": "TST", "cik_str": 42}})
        return FakeResponse({"entityName": "Test"})

    f = ei.Fetcher("Test test@example.com", opener=opener, sleep=lambda s: None)
    assert ei.resolve_ciks(f, ["TST", "NOPE"], tmp_path) == {"TST": "0000000042"}
    ei.fetch_companyfacts(f, "TST", "0000000042", tmp_path)
    ei.fetch_companyfacts(f, "TST", "0000000042", tmp_path)            # cached: no second request
    assert ei.resolve_ciks(f, ["TST"], tmp_path) == {"TST": "0000000042"}  # tickers file cached too
    assert len(calls) == 2
    assert calls[1].endswith("CIK0000000042.json")
