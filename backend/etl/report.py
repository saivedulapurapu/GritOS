"""Generated documentation for an ETL run: EDGAR_PROFILE.md, VALIDATION.md, DATASET FACTS."""
from collections import Counter

from sqlalchemy import select

import db


def input_provenance_stats(session):
    """Map every stored company-quarter and aggregate provenance + issue counts."""
    from etl.edgar_to_gritos import PROVENANCE_FIELDS, map_quarter
    from etl.validation import row_as_dict

    companies = {c.id: c for c in session.scalars(select(db.Company))}
    statuses, issues = Counter(), Counter()
    analysable = not_analysable = 0
    for q in session.scalars(select(db.QuarterlyFinancial)):
        row = row_as_dict(q)
        m = map_quarter(row, companies[q.company_id].name)
        if not m["analysable"]:
            not_analysable += 1
            for f in m["missing"]:
                issues[f"quarter not analysable: {f} missing"] += 1
            continue
        analysable += 1
        for f in PROVENANCE_FIELDS:
            statuses[m["provenance"][f]["status"]] += 1
        if m["provenance"]["ad_spend"]["status"] == "PROXY":
            issues["ad spend is a PROXY (marketing expense)"] += 1
        if m["provenance"]["ad_spend"]["status"] == "ASSUMED":
            issues["ad spend not reported (assumed 0)"] += 1
        if m["provenance"]["stock_units"]["status"] == "ASSUMED":
            issues["inventory not reported"] += 1
        for f in m["adjustments"]:
            issues["mapping adjustment (capped ad spend / fixed costs)"] += 1
        for c, d in (row["detail"] or {}).items():
            if d.get("method") in ("q4_from_fy", "q4_from_fy_minus_9m") and c == "revenue":
                issues["revenue quarter derived (Q4 = FY - Q1..Q3)"] += 1
        for c in ("operating_cash_flow", "share_based_comp", "depreciation_amortization"):
            if row[c] is None:
                issues[f"{c} missing (validation incomplete)"] += 1
    total = sum(statuses.values()) or 1
    return {
        "analysable_quarters": analysable,
        "not_analysable_quarters": not_analysable,
        "input_provenance_pct": {s: round(100 * n / total, 1) for s, n in statuses.items()},
        "input_issue_counts": dict(issues),
    }


def _kinds(stats):
    total = Counter()
    for c in stats["companies"]:
        total.update(c.get("restatements_by_kind", {}))
    return total


def _sum(stats, key):
    return sum(c[key] for c in stats["companies"])


def top_issues(stats, n=5):
    issues = Counter(stats.get("inputs", {}).get("input_issue_counts", {}))
    kinds = _kinds(stats)
    issues["values restated in a later filing"] = kinds.get("restatement", 0)
    issues["values re-reported with rounding differences"] = kinds.get("rounding", 0)
    issues["pre-listing shell facts dropped (SPAC / reverse merger)"] = _sum(stats, "dropped_pre_first_revenue_filing")
    issues["facts dropped: not 10-K/10-Q"] = sum(sum(c["dropped_forms"].values()) for c in stats["companies"])
    issues["quarters derived from YTD differencing"] = _sum(stats, "ytd_conversions")
    issues["Q4 values derived from FY"] = _sum(stats, "q4_derived")
    return [(k, v) for k, v in issues.most_common() if v][:n]


def dataset_facts(stats):
    companies = stats["companies"]
    quarters = [q for c in companies for q in c["quarters"]]
    variants = {}
    for c in companies:
        for concept, tags in c["tag_variants"].items():
            variants.setdefault(concept, set()).update(tags)
    multi = {k: sorted(v) for k, v in variants.items() if len(v) > 1}
    cells = Counter()
    for c in companies:
        cells.update(c["coverage_cells"])
    cell_total = sum(cells.values()) or 1
    v = stats["validation"]["overall"]
    inputs = stats.get("inputs", {})
    lines = [
        "=" * 64,
        "DATASET FACTS — SEC EDGAR companyfacts",
        "=" * 64,
        f"Companies loaded        : {len(companies)} ({', '.join(c['ticker'] for c in companies)})",
        f"Companies skipped       : {stats['skipped'] or 'none'}",
        f"Company-quarters        : {len(quarters)} ({min(quarters) if quarters else '-'} .. {max(quarters) if quarters else '-'})",
        f"Analysable quarters     : {inputs.get('analysable_quarters', '-')} (not analysable: {inputs.get('not_analysable_quarters', '-')})",
        f"Facts ingested (raw)    : {_sum(stats, 'facts_ingested'):,}",
        f"Facts after unit+form filter : {sum(c['facts_after_form_filter'] for c in companies):,}",
        f"Duplicates collapsed    : {_sum(stats, 'duplicates_collapsed'):,}",
        f"Restatements found      : {_sum(stats, 'restatements')} ("
        + ", ".join(f"{k} {v}" for k, v in sorted(_kinds(stats).items())) + ")",
        f"Pre-listing shell facts dropped : {_sum(stats, 'dropped_pre_first_revenue_filing')}",
        f"Q4 values derived       : {_sum(stats, 'q4_derived')}",
        f"YTD -> quarter conversions : {_sum(stats, 'ytd_conversions')}",
        f"Normalised facts stored : {_sum(stats, 'normalised_facts'):,}",
        f"Concepts with tag variants : {len(multi)} — " + "; ".join(f"{k}: {', '.join(t)}" for k, t in sorted(multi.items())),
        "Coverage (concept x quarter cells): " + ", ".join(
            f"{s} {100 * cells[s] / cell_total:.1f}%" for s in ("REAL", "DERIVED", "PROXY", "MISSING") if cells[s]),
        "GritOS input provenance (analysable quarters): " + ", ".join(
            f"{s} {p}%" for s, p in sorted(inputs.get("input_provenance_pct", {}).items(), key=lambda x: -x[1])),
        f"Validation (GritOS monthly net vs OCF/3, {v.get('quarters', 0)} quarters): "
        f"median |error| {v.get('median_abs_error_pct_revenue')}% of revenue, "
        f"mean {v.get('mean_abs_error_pct_revenue')}%; after adding back SBC + D&A: "
        f"median {v.get('median_abs_error_pct_revenue_after_addback')}%; "
        f"GritOS more pessimistic in {v.get('gritos_more_pessimistic_pct')}% of quarters; "
        f"sign agreement {v.get('sign_agreement_pct')}%",
        "Top data-quality issues:",
    ]
    lines += [f"  {i}. {k}: {n}" for i, (k, n) in enumerate(top_issues(stats), 1)]
    lines.append("=" * 64)
    return "\n".join(lines)


def write_profile(stats, path):
    out = [
        "# SEC EDGAR data profile",
        "",
        "Generated by `python -m etl.edgar_ingest --load` from the cached companyfacts JSON. Do not edit by hand.",
        "",
        "```",
        dataset_facts(stats),
        "```",
        "",
    ]
    if stats["skipped"]:
        out += ["## Skipped companies", ""] + [f"- **{t}**: {why}" for t, why in stats["skipped"].items()] + [""]
    for c in stats["companies"]:
        qs = c["quarters"]
        out += [
            f"## {c['ticker']} — {c['name']}",
            "",
            f"- Fiscal year ends: {c['fiscal_year_end']} · quarters covered: {len(qs)} ({qs[0]} .. {qs[-1]})",
            f"- Facts ingested {c['facts_ingested']:,}; non-USD dropped {c['dropped_other_units']}; "
            f"dropped forms {c['dropped_forms'] or 'none'}; after filter {c['facts_after_form_filter']:,}",
            f"- First revenue-bearing filing {c['first_revenue_filing']}; facts filed earlier (pre-listing shell) "
            f"dropped: {c['dropped_pre_first_revenue_filing']}",
            f"- Duplicates collapsed {c['duplicates_collapsed']:,} · restatements {c['restatements']} "
            f"{c['restatements_by_kind'] or ''} · "
            f"derived Q4s {c['q4_derived']} · YTD conversions {c['ytd_conversions']} · "
            f"other-duration facts ignored {c['dropped_other_durations']}",
            "",
            "| Concept | Tags used (periods) | REAL | DERIVED | PROXY | MISSING |",
            "|---|---|---|---|---|---|",
        ]
        for concept, per_q in c["coverage"].items():
            counts = Counter(per_q.values())
            tags = ", ".join(f"`{t}` ({n})" for t, n in c["tag_variants"].get(concept, {}).items()) or "—"
            out.append(f"| {concept} | {tags} | {counts['REAL']} | {counts['DERIVED']} | {counts['PROXY']} | {counts['MISSING']} |")
        gaps = sorted({q for per_q in c["coverage"].values() for q, s in per_q.items() if s == "MISSING"})
        out += ["", f"Quarters with at least one MISSING concept: {', '.join(gaps) if gaps else 'none'}", ""]
        if c["restatement_examples"]:
            out += ["Restatement examples (original -> restated, latest filing wins):", ""]
            for r in c["restatement_examples"]:
                out.append(f"- {r['concept']} `{r['tag']}` {r['period_start']}..{r['period_end']}: "
                           f"{r['original_value']:,.0f} (filed {r['original_filed']}) -> "
                           f"{r['restated_value']:,.0f} (filed {r['restated_filed']})")
            out.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")


def write_validation(summary, path):
    o = summary["overall"]
    out = [
        "# Validation: GritOS monthly net vs reported operating cash flow",
        "",
        "Generated by the ETL. For every analysable company-quarter with reported operating cash flow (OCF):",
        "",
        "- `gritos_monthly_net` = net from the GritOS engine on the mapped inputs (negative = cash burn)",
        "- `ocf_monthly` = reported OCF / 3",
        "- `error` = gritos_monthly_net - ocf_monthly (negative = GritOS shows more burn than the cash-flow statement)",
        "- errors are expressed as a % of monthly revenue so companies of different size are comparable",
        "",
        "## Result",
        "",
        f"- Quarters compared: **{o.get('quarters', 0)}**",
        f"- Mean absolute error: **${o.get('mae_usd_monthly', 0):,.0f} / month**",
        f"- |error| as % of revenue: median **{o.get('median_abs_error_pct_revenue')}%**, mean {o.get('mean_abs_error_pct_revenue')}%",
        f"- After adding back stock-based comp + D&A: median **{o.get('median_abs_error_pct_revenue_after_addback')}%**, "
        f"mean {o.get('mean_abs_error_pct_revenue_after_addback')}%",
        f"- GritOS more pessimistic than OCF in **{o.get('gritos_more_pessimistic_pct')}%** of quarters; "
        f"sign agreement (both burning / both generating cash) **{o.get('sign_agreement_pct')}%**",
        "",
        "## Why the numbers differ",
        "",
        "GritOS net equals operating income, which is an accrual measure. Operating cash flow differs by:",
        "",
        "1. **Stock-based compensation and D&A** — expenses with no cash outflow, so GritOS shows more burn. "
        "The add-back line above shows how much of the gap they explain.",
        "2. **Working capital** — inventory builds, receivables and payables timing move cash without touching operating income.",
        "3. **Items below operating income** — interest, taxes, other income.",
        "",
        "## By company",
        "",
        "| Ticker | Quarters | median abs err % rev | after add-back | more pessimistic | sign agreement |",
        "|---|---|---|---|---|---|",
    ]
    for t, b in summary["by_company"].items():
        out.append(f"| {t} | {b['quarters']} | {b['median_abs_error_pct_revenue']}% | "
                   f"{b['median_abs_error_pct_revenue_after_addback']}% | {b['gritos_more_pessimistic_pct']}% | "
                   f"{b['sign_agreement_pct']}% |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
