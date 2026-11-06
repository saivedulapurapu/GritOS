# GritOS database schema

SQLite via SQLAlchemy 2.0 (`backend/db.py`). The file is `backend/gritos.db` by default
(override with `GRITOS_DB_URL`) and is **not** committed. Tables are created on startup.
There are no migrations: after a schema change, delete `gritos.db` and it is recreated.

## Analysis tables

```mermaid
erDiagram
    businesses ||--o{ scenarios : "has"
    scenarios ||--|| results : "produces"
    results ||--o{ quality_issues : "flags"

    businesses {
        int id PK
        string name "unique with source"
        string source "manual | edgar"
        string ticker "nullable, indexed"
        datetime created_at
    }
    scenarios {
        int id PK
        int business_id FK
        datetime created_at "indexed"
        string period_label "e.g. 2025-Q3 (EDGAR)"
        string currency
        float revenue
        float ad_spend
        float cogs
        float shipping_cost
        float rto_cost
        float fixed_costs
        float cash_in_bank
        int stock_units
        float cost_per_unit
        float daily_velocity
        float top_platform_rev
        float top_supplier_spend
        float total_purchases
        float cac_shock
        float rev_shock
        float cogs_shock
        string ad_spend_behaviour
        json extra_inputs "list-valued inputs"
    }
    results {
        int id PK
        int scenario_id FK "unique"
        float grit_score
        float baseline_grit
        float runway_decay_estimate
        float baseline_runway_decay_estimate
        float runway_months "null = no cash burn"
        float shocked_runway_months "null = no cash burn"
        string fragility_tier
        string stressed_tier
        float sensitivity
        float quality_score "indexed"
        json payload "full analysis"
    }
    quality_issues {
        int id PK
        int result_id FK "indexed"
        string dimension
        string code "indexed"
        string severity
        string field
        string message
    }
```

## Why each table exists

| Table | Why |
|---|---|
| `businesses` | The thing being analysed. Separating it lets history be grouped per business and lets the same name exist once per source (a manual "Acme" and an EDGAR company never collide). |
| `scenarios` | The exact inputs and shocks of one analysis, as typed columns rather than a JSON blob, so they can be queried ("every scenario with a revenue shock above 50 %") and audited. |
| `results` | The outputs. Headline numbers are columns so the History page can chart and sort them; the full analysis is kept as JSON so any past result can be re-displayed exactly as it was returned, even if the model changes later. One result per scenario (unique FK). |
| `quality_issues` | One row per data-quality issue rather than a list inside the result, so issues can be counted and filtered across runs ("how often is ad spend above revenue?"). |

## Indexes

- `scenarios(created_at)` and `scenarios(business_id, created_at)`: the History page lists newest first, optionally for one business.
- `results(scenario_id)` unique; `results(quality_score)`: sorting by quality.
- `quality_issues(result_id)`, `quality_issues(code)`: issue lookups and counts.
- `businesses(name, source)` unique; `businesses(ticker)`.

