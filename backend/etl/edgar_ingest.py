"""
SEC EDGAR companyfacts -> normalised quarterly financials in SQLite.

Lineage: raw JSON (backend/data/raw/edgar/, gitignored) -> per-concept facts
(tag fallback) -> form filter -> restatement resolution -> quarterisation
(reported quarters, YTD differencing, Q4 = FY - (Q1+Q2+Q3)) -> quarterly_financials.
Every step is logged with counts in NormalisationLog; nothing is filled silently.

Run (from backend/):
    SEC_USER_AGENT="GritOS research you@example.com" python -m etl.edgar_ingest --fetch --load
    python -m etl.edgar_ingest --load          # re-normalise from cached raw JSON only

SEC fair access: a descriptive User-Agent with contact details is required and
requests must stay under 10 per second.
"""
import argparse
import json
import logging
import os
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger("gritos.etl")

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BACKEND_DIR / "data" / "raw" / "edgar"
DATA_DIR = BACKEND_DIR / "data"

COMPANIES = {
    "WRBY": "Warby Parker",
    "BIRD": "Allbirds",
    "FIGS": "FIGS",
    "HNST": "The Honest Company",
    "HIMS": "Hims & Hers",
    "LOVE": "Lovesac",
    "PRPL": "Purple Innovation",
    "PTON": "Peloton",
}

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
MIN_REQUEST_INTERVAL_S = 0.15  # < 7 requests/s, under SEC's 10/s limit
PLACEHOLDER_USER_AGENT_EMAIL = "you@example.com"  # the value shipped in .env.example

# Concept -> XBRL tags in priority order. For each period the first tag with a value wins.
CONCEPTS = {
    "revenue": ("flow", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                         "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]),
    "cogs": ("flow", ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]),
    "operating_income": ("flow", ["OperatingIncomeLoss"]),
    "advertising": ("flow", ["AdvertisingExpense"]),  # annual (10-K note) only
    "marketing": ("flow", ["MarketingExpense", "MarketingAndAdvertisingExpense", "SellingAndMarketingExpense"]),
    "general_admin": ("flow", ["GeneralAndAdministrativeExpense"]),
    "research_dev": ("flow", ["ResearchAndDevelopmentExpense"]),
    "sga": ("flow", ["SellingGeneralAndAdministrativeExpense"]),
    "cash": ("instant", ["CashAndCashEquivalentsAtCarryingValue",
                         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    "inventory": ("instant", ["InventoryNet", "RetailRelatedInventoryMerchandise",
                              "InventoryFinishedGoodsNetOfReserves", "InventoryFinishedGoods"]),
    "operating_cash_flow": ("flow", ["NetCashProvidedByUsedInOperatingActivities"]),
    "share_based_comp": ("flow", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    "depreciation_amortization": ("flow", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"]),
}

KEPT_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}
UNIT = "USD"

# Duration classes (days between start and end, inclusive of 52/53-week calendars)
DURATION_CLASSES = [("Q", 80, 100), ("H1", 170, 190), ("9M", 260, 285), ("FY", 350, 380)]
CHAIN_TOLERANCE_DAYS = 3


# ---------------------------------------------------------------------------
# Fetch (network) — never called by tests
# ---------------------------------------------------------------------------

class Fetcher:
    def __init__(self, user_agent, opener=urllib.request.urlopen, sleep=time.sleep, clock=time.monotonic):
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT must be set to a descriptive name with a contact email")
        if PLACEHOLDER_USER_AGENT_EMAIL in user_agent:
            raise ValueError("SEC_USER_AGENT still holds the .env.example placeholder; use your own contact email")
        self.user_agent = user_agent
        self._open, self._sleep, self._clock = opener, sleep, clock
        self._last = None
        self.requests = 0

    def get_json(self, url):
        if self._last is not None:
            wait = MIN_REQUEST_INTERVAL_S - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        with self._open(req, timeout=60) as resp:
            body = resp.read()
        self._last = self._clock()
        self.requests += 1
        return json.loads(body.decode("utf-8"))


def resolve_ciks(fetcher, tickers, cache_dir=RAW_DIR):
    path = Path(cache_dir) / "company_tickers.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = fetcher.get_json(TICKERS_URL)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    by_ticker = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
    return {t: by_ticker[t] for t in tickers if t in by_ticker}


def fetch_companyfacts(fetcher, ticker, cik, cache_dir=RAW_DIR, refresh=False):
    path = Path(cache_dir) / f"{ticker}.json"
    if path.exists() and not refresh:
        return path
    data = fetcher.get_json(FACTS_URL.format(cik=cik))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Normalisation (pure functions — every rule is unit-tested)
# ---------------------------------------------------------------------------

@dataclass
class Fact:
    concept: str
    tag: str
    start: date | None
    end: date
    value: float
    form: str
    filed: date
    accn: str
    provenance: str = "REAL"
    method: str = "reported"

    @property
    def period(self):
        return (self.start, self.end)


@dataclass
class NormalisationLog:
    facts_ingested: int = 0
    dropped_other_units: int = 0
    dropped_forms: Counter = field(default_factory=Counter)
    duplicates_collapsed: int = 0
    restatements: list = field(default_factory=list)
    dropped_other_durations: int = 0
    tag_variants: dict = field(default_factory=dict)       # concept -> {tag: periods}
    dropped_pre_first_revenue_filing: int = 0
    first_revenue_filing: date | None = None
    ytd_conversions: int = 0
    q4_derived: int = 0
    quarter_key_collisions: int = 0

    @property
    def facts_after_form_filter(self):
        return self.facts_ingested - self.dropped_other_units - sum(self.dropped_forms.values())


def parse_date(s):
    return date.fromisoformat(s) if s else None


def extract_tag_facts(companyfacts, concept, tag, log):
    """All facts for one tag, USD only. Other units (e.g. shares) are dropped and counted."""
    node = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return []
    out = []
    for unit, rows in node.get("units", {}).items():
        for r in rows:
            log.facts_ingested += 1
            if unit != UNIT:
                log.dropped_other_units += 1
                continue
            out.append(Fact(concept, tag, parse_date(r.get("start")), parse_date(r["end"]), float(r["val"]),
                            r.get("form", ""), parse_date(r["filed"]), r.get("accn", "")))
    return out


def filter_forms(facts, log):
    """Keep 10-K / 10-Q (and their amendments). Drops DEF 14A, 8-K, S-1 ... duplicates."""
    kept = []
    for f in facts:
        if f.form in KEPT_FORMS:
            kept.append(f)
        else:
            log.dropped_forms[f.form] += 1
    return kept


RESTATEMENT_ROUNDING_REL = 0.001   # <= 0.1 % difference: precision / rounding
RESTATEMENT_SCALE_RATIO = 10       # >= 10x: unit error or a different reporting entity


def restatement_kind(original, restated):
    a, b = abs(original), abs(restated)
    if abs(restated - original) <= max(a, 1) * RESTATEMENT_ROUNDING_REL:
        return "rounding"
    lo, hi = min(a, b), max(a, b)
    if lo == 0 or hi / lo >= RESTATEMENT_SCALE_RATIO:
        return "scale_or_entity"
    return "restatement"


def drop_pre_first_revenue_filings(facts, first_revenue_filed, log):
    """Drop facts filed before the company's first filing that reports revenue.
    Companies that listed through a SPAC / reverse merger (e.g. Hims & Hers, Purple) inherit the
    shell's earlier filings under the same CIK; those facts describe a different entity. For a
    normal IPO the first filing already reports revenue, so nothing is dropped."""
    if first_revenue_filed is None:
        return facts
    kept = [f for f in facts if f.filed >= first_revenue_filed]
    log.dropped_pre_first_revenue_filing += len(facts) - len(kept)
    return kept


def resolve_restatements(facts, log):
    """One value per (tag, period). Same value in several filings -> collapsed.
    Different values -> the latest filed wins; every superseded value is recorded."""
    groups = defaultdict(list)
    for f in facts:
        groups[(f.tag, f.start, f.end)].append(f)
    out = []
    for (_tag, _s, _e), group in groups.items():
        group.sort(key=lambda f: (f.filed, f.accn))
        final = group[-1]
        seen_values = set()
        for g in group[:-1]:
            if g.value == final.value or g.value in seen_values:
                log.duplicates_collapsed += 1
                continue
            seen_values.add(g.value)
            log.restatements.append({
                "kind": restatement_kind(g.value, final.value),
                "concept": final.concept, "tag": final.tag, "period_start": final.start, "period_end": final.end,
                "original_value": g.value, "original_filed": g.filed, "original_accn": g.accn,
                "restated_value": final.value, "restated_filed": final.filed, "restated_accn": final.accn,
            })
        out.append(final)
    return out


def duration_class(f):
    if f.start is None:
        return "instant"
    days = (f.end - f.start).days
    for name, lo, hi in DURATION_CLASSES:
        if lo <= days <= hi:
            return name
    return "other"


def select_tags(facts_by_tag, tags, concept, log):
    """Per period, use the highest-priority tag that reports it. Records which tags were used."""
    chosen = {}
    for tag in tags:
        for f in facts_by_tag.get(tag, []):
            chosen.setdefault(f.period, f)
    used = Counter(f.tag for f in chosen.values())
    if used:
        log.tag_variants[concept] = dict(used)
    return list(chosen.values())


def quarter_key(end):
    """Calendar quarter of the period end, shifted 15 days back so 52/53-week quarter ends
    (e.g. Lovesac 2025-02-02, 2025-05-04) land in the quarter they mostly cover."""
    d = end - timedelta(days=15)
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def _near(a, b, tol=CHAIN_TOLERANCE_DAYS):
    return a is not None and b is not None and abs((a - b).days) <= tol


def quarterize_flow(facts, log):
    """Flow concept -> one value per fiscal quarter.
    1. Reported quarters (~90-day facts) are REAL.
    2. For each fiscal year start S, cumulative facts starting at S (3M, H1, 9M, FY) give
       missing quarters by differencing: Q2 = H1 - 3M, Q3 = 9M - H1 (method ytd_difference).
    3. Q4 = FY - (Q1 + Q2 + Q3) when all three are known, else FY - 9M (method q4_from_fy*).
    Returns {period_end: Fact}."""
    classified = [(duration_class(f), f) for f in facts]
    for cls, _f in classified:
        if cls in ("other", "instant"):
            log.dropped_other_durations += 1
    quarters = [f for c, f in classified if c == "Q"]
    out = {f.end: f for f in quarters}

    by_start = defaultdict(dict)
    for c, f in classified:
        if c in ("Q", "H1", "9M", "FY"):
            by_start[f.start][c] = f

    def find_quarter_starting(s):
        for q in quarters:
            if _near(q.start, s):
                return q
        return None

    for s, group in sorted(by_start.items()):
        if not any(k in group for k in ("H1", "9M", "FY")):
            continue  # a lone quarter, already handled
        cum = [group.get("Q"), group.get("H1"), group.get("9M"), group.get("FY")]
        starts, ends = [s, None, None, None], [None, None, None, None]
        for k in range(4):
            if k > 0 and ends[k - 1] is not None:
                starts[k] = ends[k - 1] + timedelta(days=1)
            if cum[k] is not None:
                ends[k] = cum[k].end
            elif starts[k] is not None:
                q = find_quarter_starting(starts[k])
                if q is not None:
                    ends[k] = q.end
        values = [None, None, None, None]
        for k in range(4):
            if ends[k] is None:
                continue
            reported = out.get(ends[k])
            if reported is not None and reported.method == "reported":
                values[k] = reported
                continue
            derived = None
            template = (cum[k] or cum[k - 1]) if k > 0 else None
            if 0 < k < 3 and cum[k] is not None and cum[k - 1] is not None:
                derived = (cum[k].value - cum[k - 1].value, "ytd_difference")
                log.ytd_conversions += 1
            elif 0 < k < 3 and cum[k] is not None and all(v is not None for v in values[:k]):
                derived = (cum[k].value - sum(v.value for v in values[:k]), "ytd_difference")
                log.ytd_conversions += 1
            elif k == 3 and cum[3] is not None:
                if all(v is not None for v in values[:3]):
                    derived = (cum[3].value - sum(v.value for v in values[:3]), "q4_from_fy")
                    log.q4_derived += 1
                elif cum[2] is not None:
                    derived = (cum[3].value - cum[2].value, "q4_from_fy_minus_9m")
                    log.q4_derived += 1
            if derived is not None and template is not None:
                f = Fact(template.concept, template.tag, starts[k], ends[k], derived[0], template.form,
                         template.filed, template.accn, provenance="DERIVED", method=derived[1])
                out[ends[k]] = f
                values[k] = f
    return out


def annual_facts(facts):
    """FY-duration facts only (used for AdvertisingExpense, which is disclosed annually)."""
    return {f.end: f for f in facts if duration_class(f) == "FY"}


def instant_facts(facts):
    return {f.end: f for f in facts if f.start is None}


@dataclass
class CompanyData:
    ticker: str
    cik: str
    name: str
    fiscal_year_end: str | None
    quarters: dict          # quarter key -> {concept: Fact | None, "_start", "_end"}
    annual_advertising: dict  # FY end -> Fact
    facts: list             # all normalised facts written to financial_facts
    log: NormalisationLog


def normalise_company(companyfacts, ticker, cik=None):
    log = NormalisationLog()
    per_concept = {}
    all_facts = []
    annual_ads = {}
    kept_by_concept = {}
    for concept, (_kind, tags) in CONCEPTS.items():
        kept_by_concept[concept] = {tag: filter_forms(extract_tag_facts(companyfacts, concept, tag, log), log)
                                    for tag in tags}
    revenue_filed = [f.filed for facts in kept_by_concept["revenue"].values() for f in facts]
    log.first_revenue_filing = min(revenue_filed) if revenue_filed else None

    for concept, (kind, tags) in CONCEPTS.items():
        by_tag = {}
        for tag in tags:
            kept = drop_pre_first_revenue_filings(kept_by_concept[concept][tag], log.first_revenue_filing, log)
            by_tag[tag] = resolve_restatements(kept, log)
        selected = select_tags(by_tag, tags, concept, log)
        if concept == "advertising":
            annual_ads = annual_facts(selected)
            all_facts.extend(annual_ads.values())
            continue
        series = instant_facts(selected) if kind == "instant" else quarterize_flow(selected, log)
        per_concept[concept] = series
        all_facts.extend(series.values())

    # Quarter universe: periods where revenue exists (the quarters the company reports on)
    quarters = {}
    for end, rev in sorted(per_concept.get("revenue", {}).items()):
        key = quarter_key(end)
        if key in quarters:
            log.quarter_key_collisions += 1
            continue
        row = {"_start": rev.start, "_end": end}
        for concept in CONCEPTS:
            if concept == "advertising":
                continue
            series = per_concept.get(concept, {})
            match = series.get(end)
            if match is None:  # balance-sheet dates can differ by a day or two from the P&L period end
                match = next((v for e, v in series.items() if _near(e, end)), None)
            row[concept] = match
        quarters[key] = row

    fy_end = _latest_fiscal_year_end(companyfacts)
    return CompanyData(ticker, cik or str(companyfacts.get("cik", "")).zfill(10),
                       companyfacts.get("entityName", ticker), fy_end, quarters, annual_ads, all_facts, log)


def _latest_fiscal_year_end(companyfacts):
    node = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag in CONCEPTS["revenue"][1]:
        rows = [r for rows in node.get(tag, {}).get("units", {}).values() for r in rows
                if r.get("form") == "10-K" and r.get("start")]
        fys = [r for r in rows if DURATION_CLASSES[3][1] <= (parse_date(r["end"]) - parse_date(r["start"])).days <= DURATION_CLASSES[3][2]]
        if fys:
            return max(r["end"] for r in fys)[5:]
    return None


def advertising_for_quarter(annual_ads, quarter_end):
    """The FY AdvertisingExpense whose fiscal year contains this quarter, or None."""
    for fy_end, f in annual_ads.items():
        if f.start <= quarter_end <= fy_end + timedelta(days=CHAIN_TOLERANCE_DAYS):
            return f
    return None


def coverage_matrix(company):
    """concept -> quarter -> REAL | DERIVED | PROXY | MISSING.
    advertising: DERIVED when an annual figure covers the quarter (allocated), PROXY when
    only quarterly marketing expense exists, MISSING otherwise."""
    matrix = defaultdict(dict)
    for key, row in company.quarters.items():
        for concept in CONCEPTS:
            if concept == "advertising":
                if advertising_for_quarter(company.annual_advertising, row["_end"]):
                    status = "DERIVED"
                elif row.get("marketing") is not None:
                    status = "PROXY"
                else:
                    status = "MISSING"
            else:
                f = row.get(concept)
                status = f.provenance if f is not None else "MISSING"
            matrix[concept][key] = status
    return matrix


# ---------------------------------------------------------------------------
# Load into SQLite
# ---------------------------------------------------------------------------

def load_company(session, company):
    """Replace this company's EDGAR rows with the freshly normalised data."""
    from sqlalchemy import delete, select

    import db

    existing = session.scalar(select(db.Company).where(db.Company.ticker == company.ticker))
    if existing is not None:
        for model in (db.ValidationResult, db.QuarterlyFinancial, db.FinancialFact, db.Restatement, db.Filing):
            session.execute(delete(model).where(model.company_id == existing.id))
        row = existing
        row.name, row.cik, row.fiscal_year_end = company.name, company.cik, company.fiscal_year_end
    else:
        row = db.Company(ticker=company.ticker, cik=company.cik, name=company.name,
                         fiscal_year_end=company.fiscal_year_end, currency="USD")
        session.add(row)
    session.flush()

    filings = {}
    for f in company.facts:
        if f.provenance == "REAL" and f.accn and f.accn not in filings:
            filing = session.scalar(select(db.Filing).where(db.Filing.accn == f.accn))
            if filing is None:
                filing = db.Filing(company_id=row.id, accn=f.accn, form=f.form, filed_date=f.filed)
                session.add(filing)
            filings[f.accn] = filing
    session.flush()

    for f in company.facts:
        kind = "instant" if f.start is None else ("annual" if duration_class(f) == "FY" else "quarter")
        session.add(db.FinancialFact(
            company_id=row.id,
            filing_id=filings[f.accn].id if f.provenance == "REAL" and f.accn in filings else None,
            concept=f.concept, tag_used=f.tag, period_start=f.start, period_end=f.end, period_type=kind,
            quarter=quarter_key(f.end) if kind != "annual" else None, value=f.value, unit=UNIT,
            form=f.form, filed_date=f.filed, provenance=f.provenance, method=f.method,
        ))
    for r in company.log.restatements:
        session.add(db.Restatement(company_id=row.id, **r))

    for key, q in company.quarters.items():
        ads = advertising_for_quarter(company.annual_advertising, q["_end"])
        values = {c: (q[c].value if q.get(c) is not None else None) for c in CONCEPTS if c != "advertising"}
        prov = {c: (q[c].provenance if q.get(c) is not None else "MISSING") for c in CONCEPTS if c != "advertising"}
        prov["advertising"] = "REAL" if ads else "MISSING"
        detail = {c: {"tag": q[c].tag, "method": q[c].method, "filed": q[c].filed.isoformat()}
                  for c in CONCEPTS if c != "advertising" and q.get(c) is not None}
        if ads:
            detail["advertising"] = {"tag": ads.tag, "method": "annual", "filed": ads.filed.isoformat(),
                                     "fiscal_year_end": ads.end.isoformat()}
        session.add(db.QuarterlyFinancial(
            company_id=row.id, quarter=key, period_start=q["_start"], period_end=q["_end"],
            revenue=values["revenue"], cogs=values["cogs"], operating_income=values["operating_income"],
            advertising_annual=ads.value if ads else None, marketing=values["marketing"],
            general_admin=values["general_admin"], research_dev=values["research_dev"], sga=values["sga"],
            cash=values["cash"], inventory=values["inventory"], operating_cash_flow=values["operating_cash_flow"],
            share_based_comp=values["share_based_comp"],
            depreciation_amortization=values["depreciation_amortization"],
            provenance=prov, detail=detail,
        ))
    session.flush()
    return row


def company_stats(company):
    log = company.log
    matrix = coverage_matrix(company)
    cells = Counter(s for per_q in matrix.values() for s in per_q.values())
    return {
        "ticker": company.ticker,
        "name": company.name,
        "fiscal_year_end": company.fiscal_year_end,
        "quarters": sorted(company.quarters),
        "facts_ingested": log.facts_ingested,
        "dropped_other_units": log.dropped_other_units,
        "dropped_forms": dict(log.dropped_forms),
        "facts_after_form_filter": log.facts_after_form_filter,
        "duplicates_collapsed": log.duplicates_collapsed,
        "restatements": len(log.restatements),
        "restatements_by_kind": dict(Counter(r["kind"] for r in log.restatements)),
        "first_revenue_filing": log.first_revenue_filing.isoformat() if log.first_revenue_filing else None,
        "dropped_pre_first_revenue_filing": log.dropped_pre_first_revenue_filing,
        "restatement_examples": [
            {k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in log.restatements[:3]
        ],
        "dropped_other_durations": log.dropped_other_durations,
        "ytd_conversions": log.ytd_conversions,
        "q4_derived": log.q4_derived,
        "quarter_key_collisions": log.quarter_key_collisions,
        "tag_variants": log.tag_variants,
        "normalised_facts": len(company.facts),
        "coverage_cells": dict(cells),
        "coverage": {c: dict(v) for c, v in matrix.items()},
    }


def run(tickers, raw_dir=RAW_DIR, session_factory=None, fetch=False, refresh=False, user_agent=None,
        write_docs=True, docs_dir=DATA_DIR):
    """Normalise (and optionally fetch) every ticker, load into the DB, compute validation,
    write EDGAR_PROFILE.md / VALIDATION.md. Returns the run stats."""
    import db
    from etl import validation

    raw_dir = Path(raw_dir)
    if fetch:
        fetcher = Fetcher(user_agent or os.getenv("SEC_USER_AGENT", ""))
        ciks = resolve_ciks(fetcher, tickers, raw_dir)
        for t in tickers:
            if t in ciks:
                fetch_companyfacts(fetcher, t, ciks[t], raw_dir, refresh=refresh)
            else:
                logger.warning("%s: not in SEC ticker list, skipped", t)
    session_factory = session_factory or db.SessionLocal
    db.init_db(session_factory.kw["bind"])

    stats = {"companies": [], "skipped": {}}
    with session_factory() as session:
        for t in tickers:
            path = raw_dir / f"{t}.json"
            if not path.exists():
                stats["skipped"][t] = "no raw companyfacts file (run with --fetch)"
                continue
            company = normalise_company(json.loads(path.read_text(encoding="utf-8")), t)
            if not company.quarters:
                stats["skipped"][t] = "no usable quarterly revenue facts"
                continue
            load_company(session, company)
            stats["companies"].append(company_stats(company))
        session.flush()
        stats["validation"] = validation.compute_and_store(session)
        from etl import report
        stats["inputs"] = report.input_provenance_stats(session)
        session.add(db.EtlRun(stats=_jsonable(stats)))
        session.commit()

    if write_docs:
        from etl import report
        report.write_profile(stats, Path(docs_dir) / "EDGAR_PROFILE.md")
        report.write_validation(stats["validation"], Path(docs_dir) / "VALIDATION.md")
    return stats


def _jsonable(obj):
    return json.loads(json.dumps(obj, default=str))


def main(argv=None):
    from dotenv import load_dotenv

    load_dotenv()  # SEC_USER_AGENT / GRITOS_DB_URL may live in .env
    parser = argparse.ArgumentParser(description="Load SEC EDGAR companyfacts into GritOS")
    parser.add_argument("--tickers", default=",".join(COMPANIES), help="comma-separated tickers")
    parser.add_argument("--fetch", action="store_true", help="download missing raw files from SEC")
    parser.add_argument("--refresh", action="store_true", help="re-download even if cached")
    parser.add_argument("--load", action="store_true", help="normalise cached raw files into the database")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not (args.fetch or args.load):
        parser.error("nothing to do: pass --fetch and/or --load")
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    stats = run(tickers, fetch=args.fetch, refresh=args.refresh)
    from etl import report
    print(report.dataset_facts(stats))


if __name__ == "__main__":
    main()
