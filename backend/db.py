"""
SQLite persistence (SQLAlchemy 2.0 ORM). Schema and the reason for each table: SCHEMA.md.

The database file defaults to backend/gritos.db (gitignored) and can be moved with
GRITOS_DB_URL. Tables are created on startup; there are no migrations, so after a
schema change delete gritos.db and it is recreated (EDGAR data is reloaded by the ETL).
"""
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine,
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
    ticker: Mapped[str | None] = mapped_column(String(10), index=True)
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
