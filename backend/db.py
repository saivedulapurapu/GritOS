"""
SQLite persistence (SQLAlchemy 2.0 ORM). Schema and the reason for each table: SCHEMA.md.

The database file defaults to backend/gritos.db (gitignored) and can be moved with
GRITOS_DB_URL. Tables are created on startup; there are no migrations, so after a
schema change delete gritos.db and it is recreated (EDGAR data is reloaded by the ETL).
"""
import os
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "gritos.db"


def db_url():
    return os.getenv("GRITOS_DB_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("name", "source", name="uq_business_name_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(10))  # "manual" | "edgar"
    ticker: Mapped[str | None] = mapped_column(ForeignKey("companies.ticker"), index=True)  # EDGAR only
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scenarios: Mapped[list["Scenario"]] = relationship(back_populates="business")


class Scenario(Base):
    """One set of inputs + shocks that was analysed."""
    __tablename__ = "scenarios"
    __table_args__ = (Index("ix_scenarios_business_created", "business_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    period_label: Mapped[str | None] = mapped_column(String(10))  # e.g. "2025-Q3" for EDGAR
    currency: Mapped[str] = mapped_column(String(3))

    revenue: Mapped[float] = mapped_column(Float)
    ad_spend: Mapped[float] = mapped_column(Float)
    cogs: Mapped[float] = mapped_column(Float)
    shipping_cost: Mapped[float] = mapped_column(Float)
    rto_cost: Mapped[float] = mapped_column(Float)
    fixed_costs: Mapped[float] = mapped_column(Float)
    cash_in_bank: Mapped[float] = mapped_column(Float)
    stock_units: Mapped[int] = mapped_column(Integer)
    cost_per_unit: Mapped[float] = mapped_column(Float)
    daily_velocity: Mapped[float] = mapped_column(Float)
    top_platform_rev: Mapped[float] = mapped_column(Float)
    top_supplier_spend: Mapped[float] = mapped_column(Float)
    total_purchases: Mapped[float] = mapped_column(Float)

    cac_shock: Mapped[float] = mapped_column(Float)
    rev_shock: Mapped[float] = mapped_column(Float)
    cogs_shock: Mapped[float] = mapped_column(Float)
    ad_spend_behaviour: Mapped[str] = mapped_column(String(10))

    extra_inputs: Mapped[dict | None] = mapped_column(JSON)  # list-valued inputs (concentration shares)

    business: Mapped[Business] = relationship(back_populates="scenarios")
    result: Mapped["Result"] = relationship(back_populates="scenario", uselist=False, cascade="all, delete-orphan")


class Result(Base):
    """Headline outputs as columns (queryable, chartable) + the full analysis as JSON."""
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), unique=True)
    grit_score: Mapped[float] = mapped_column(Float)
    baseline_grit: Mapped[float] = mapped_column(Float)
    runway_decay_estimate: Mapped[float] = mapped_column(Float)
    baseline_runway_decay_estimate: Mapped[float] = mapped_column(Float)
    runway_months: Mapped[float | None] = mapped_column(Float)          # None = no cash burn
    shocked_runway_months: Mapped[float | None] = mapped_column(Float)  # None = no cash burn
    fragility_tier: Mapped[str] = mapped_column(String(12))
    stressed_tier: Mapped[str] = mapped_column(String(12))
    sensitivity: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict] = mapped_column(JSON)

    scenario: Mapped[Scenario] = relationship(back_populates="result")
    quality_issues: Mapped[list["QualityIssue"]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )


class QualityIssue(Base):
    """One row per data-quality issue, so issues can be counted and filtered across runs."""
    __tablename__ = "quality_issues"
    __table_args__ = (Index("ix_quality_issues_code", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id", ondelete="CASCADE"), index=True)
    dimension: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    field: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)

    result: Mapped[Result] = relationship(back_populates="quality_issues")


# ---------------------------------------------------------------------------
# SEC EDGAR tables (loaded by etl/edgar_ingest.py)
# ---------------------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    fiscal_year_end: Mapped[str | None] = mapped_column(String(5))  # "MM-DD" of latest FY end
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    accn: Mapped[str] = mapped_column(String(25), unique=True)
    form: Mapped[str] = mapped_column(String(10))
    filed_date: Mapped[date] = mapped_column(Date)


class FinancialFact(Base):
    """One normalised value: reported (REAL, linked to its filing) or computed (DERIVED, with method)."""
    __tablename__ = "financial_facts"
    __table_args__ = (
        UniqueConstraint("company_id", "concept", "period_start", "period_end", name="uq_fact_period"),
        Index("ix_facts_company_concept_end", "company_id", "concept", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    filing_id: Mapped[int | None] = mapped_column(ForeignKey("filings.id"))  # None for DERIVED
    concept: Mapped[str] = mapped_column(String(30))
    tag_used: Mapped[str] = mapped_column(String(120))
    period_start: Mapped[date | None] = mapped_column(Date)  # None for instant (balance sheet) facts
    period_end: Mapped[date] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(8))  # quarter | annual | instant
    quarter: Mapped[str | None] = mapped_column(String(7), index=True)  # "YYYY-Qn" (by period end)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))
    form: Mapped[str | None] = mapped_column(String(10))
    filed_date: Mapped[date | None] = mapped_column(Date)
    provenance: Mapped[str] = mapped_column(String(8))  # REAL | DERIVED
    method: Mapped[str] = mapped_column(String(30))  # reported | ytd_difference | q4_from_fy | q4_from_fy_minus_9m


class Restatement(Base):
    """A period reported with different values in different filings; the latest filed value is used."""
    __tablename__ = "restatements"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # rounding | restatement | scale_or_entity
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    concept: Mapped[str] = mapped_column(String(30))
    tag: Mapped[str] = mapped_column(String(120))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    original_value: Mapped[float] = mapped_column(Float)
    original_filed: Mapped[date] = mapped_column(Date)
    original_accn: Mapped[str] = mapped_column(String(25))
    restated_value: Mapped[float] = mapped_column(Float)
    restated_filed: Mapped[date] = mapped_column(Date)
    restated_accn: Mapped[str] = mapped_column(String(25))


class QuarterlyFinancial(Base):
    """Wide, analysis-ready table: one row per company-quarter, every value with its provenance."""
    __tablename__ = "quarterly_financials"
    __table_args__ = (UniqueConstraint("company_id", "quarter", name="uq_company_quarter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    quarter: Mapped[str] = mapped_column(String(7))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    revenue: Mapped[float | None] = mapped_column(Float)
    cogs: Mapped[float | None] = mapped_column(Float)
    operating_income: Mapped[float | None] = mapped_column(Float)
    advertising_annual: Mapped[float | None] = mapped_column(Float)  # FY AdvertisingExpense covering this quarter
    marketing: Mapped[float | None] = mapped_column(Float)
    general_admin: Mapped[float | None] = mapped_column(Float)
    research_dev: Mapped[float | None] = mapped_column(Float)
    sga: Mapped[float | None] = mapped_column(Float)
    cash: Mapped[float | None] = mapped_column(Float)
    inventory: Mapped[float | None] = mapped_column(Float)
    operating_cash_flow: Mapped[float | None] = mapped_column(Float)
    share_based_comp: Mapped[float | None] = mapped_column(Float)
    depreciation_amortization: Mapped[float | None] = mapped_column(Float)
    provenance: Mapped[dict] = mapped_column(JSON)  # concept -> REAL | DERIVED | MISSING
    detail: Mapped[dict] = mapped_column(JSON)      # concept -> {tag, method, filed}


class ValidationResult(Base):
    """GritOS monthly net (cash burn when negative) vs reported operating cash flow / 3."""
    __tablename__ = "validation_results"
    __table_args__ = (UniqueConstraint("company_id", "quarter", name="uq_validation_company_quarter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    quarter: Mapped[str] = mapped_column(String(7))
    gritos_monthly_net: Mapped[float] = mapped_column(Float)
    ocf_monthly: Mapped[float] = mapped_column(Float)
    revenue_monthly: Mapped[float] = mapped_column(Float)
    noncash_addback_monthly: Mapped[float | None] = mapped_column(Float)  # (SBC + D&A) / 3


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stats: Mapped[dict] = mapped_column(JSON)


def make_engine(url=None):
    url = url or db_url()
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind=None):
    Base.metadata.create_all(bind or engine)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
