"""
Request schemas — the HARD data-quality rules.

Anything that breaks these rules is rejected with HTTP 422 before any model runs:
- money and quantity fields are finite and >= 0
- shocks are bounded: revenue drop 0-100 %, cost increases (CAC, COGS) 0-300 %
- cross-field: top-platform revenue <= revenue; top-supplier spend <= total purchases;
  stock on hand needs a sales velocity > 0 (otherwise days-to-sell-through is undefined)
- unknown fields are rejected (catches typos and renamed fields such as the old kak_shock)

Softer checks (possible but suspicious inputs, implausible outputs) are not errors;
they are reported by data_quality.py.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$"}

MAX_REVENUE_DROP_PCT = 100
MAX_COST_INCREASE_PCT = 300


class FullBusinessState(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    business_name: str = Field("Manual scenario", min_length=1, max_length=120)
    currency: Literal["INR", "USD"] = "INR"

    # Baseline (monthly)
    revenue: float = Field(ge=0)
    ad_spend: float = Field(ge=0)
    cogs: float = Field(ge=0)
    shipping_cost: float = Field(ge=0)
    rto_cost: float = Field(0, ge=0)
    fixed_costs: float = Field(ge=0)
    cash_in_bank: float = Field(ge=0)

    # Shocks (percent)
    cac_shock: float = Field(0, ge=0, le=MAX_COST_INCREASE_PCT)
    rev_shock: float = Field(0, ge=0, le=MAX_REVENUE_DROP_PCT)
    cogs_shock: float = Field(0, ge=0, le=MAX_COST_INCREASE_PCT)
    ad_spend_behaviour: Literal["fixed", "scales"] = "fixed"  # see shock_engine.apply_shocks

    # Inventory
    stock_units: int = Field(1000, ge=0)
    cost_per_unit: float = Field(500, ge=0)
    daily_velocity: float = Field(10, ge=0)

    # Concentration (0 = not supplied)
    top_platform_rev: float = Field(0, ge=0)
    top_supplier_spend: float = Field(0, ge=0)
    total_purchases: float = Field(0, ge=0)

    @model_validator(mode="after")
    def check_cross_field_rules(self):
        problems = []
        if self.top_platform_rev > self.revenue:
            problems.append(
                f"top_platform_rev ({self.top_platform_rev:,.2f}) cannot exceed revenue ({self.revenue:,.2f})"
            )
        if self.top_supplier_spend > self.total_purchases:
            problems.append(
                f"top_supplier_spend ({self.top_supplier_spend:,.2f}) cannot exceed "
                f"total_purchases ({self.total_purchases:,.2f})"
            )
        if self.stock_units > 0 and self.daily_velocity <= 0:
            problems.append("daily_velocity must be > 0 when stock_units > 0")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "model", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=50)  # empty list -> 422
    state: FullBusinessState
