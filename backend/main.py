from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Literal

# Import local modules
import financial_engine
import shock_engine
import capital_lock
import dependency_index
import fragility_model
import grit
import llm_advisor
import runway_decay

app = FastAPI(title="GritOS Runway Intelligence API")

@app.get("/")
async def health_check():
    return {"status": "online", "version": "2.0"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"DEBUG: Validation Error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

import mock_data

class FullBusinessState(BaseModel):
    # Baseline
    revenue: float
    ad_spend: float
    cogs: float
    shipping_cost: float
    rto_cost: float = 0
    fixed_costs: float
    cash_in_bank: float
    # Shocks
    kak_shock: float = 0
    rev_shock: float = 0
    cogs_shock: float = 0
    ad_spend_behaviour: Literal["fixed", "scales"] = "fixed"  # see shock_engine.apply_shocks
    # Inventory (Component 3)
    stock_units: int = 1000
    cost_per_unit: float = 500
    daily_velocity: float = 10
    # Dependency (Component 4)
    top_platform_rev: float = 800000
    top_supplier_spend: float = 200000
    total_purchases: float = 300000

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)  # empty list -> 422, not IndexError
    state: FullBusinessState

def process_business_state(state: FullBusinessState):
    # 1. Baseline calc
    baseline = financial_engine.calculate_operational_metrics(
        state.revenue, state.ad_spend, state.cogs, state.shipping_cost, state.rto_cost
    )
    bottom_line = financial_engine.calculate_net_metrics(baseline['contribution_margin'], state.fixed_costs, state.cash_in_bank)
    
    # 2. Shock Simulation
    shock_results = shock_engine.apply_shocks(
        state.dict(), state.kak_shock, state.rev_shock, state.cogs_shock, state.ad_spend_behaviour
    )
    
    # 3. Capital Lock
    lock_data = capital_lock.calculate_capital_lock(state.stock_units, state.cost_per_unit, state.daily_velocity)
    
    # 4. Fragility tier (baseline structure) & shock sensitivity
    ad_spend_ratio = state.ad_spend / state.revenue if state.revenue > 0 else 0
    total_shock_pct = state.kak_shock + state.rev_shock + state.cogs_shock

    fragility = fragility_model.classify_fragility(baseline['margin_percent'], bottom_line['runway_months'], ad_spend_ratio)
    sensitivity = fragility_model.get_shock_sensitivity(bottom_line['runway_months'], shock_results['runway'], total_shock_pct)
    fragility['sensitivity'] = sensitivity
    shock_results['runway_lost_months'] = fragility_model.runway_lost_within_horizon(
        bottom_line['runway_months'], shock_results['runway']
    )

    # Same rules on the shocked figures: how the business looks under this scenario.
    stressed = fragility_model.classify_fragility(
        shock_results['margin_percent'], shock_results['runway'], shock_results['ad_spend_ratio']
    )
    fragility['stressed_class'] = stressed['class']
    fragility['stressed_reasons'] = stressed['reasons']

    # 5. Runway-decay estimate: λ = runway x BASELINE tier factor (<= runway).
    # Sensitivity is reported, not used here. The scenario estimate uses the SHOCKED
    # runway; the baseline estimate (no shock) feeds the Grit Score.
    runway_decay_estimate = runway_decay.calculate_runway_decay_estimate(shock_results['runway'], fragility['class'])
    trajectory = runway_decay.calculate_runway_decay_trajectory(shock_results['runway'], fragility['class'])
    baseline_runway_decay_estimate = runway_decay.calculate_runway_decay_estimate(bottom_line['runway_months'], fragility['class'])

    # 6. Dependency
    dependency = dependency_index.get_dependency_score(
        state.top_platform_rev, state.revenue, state.top_supplier_spend, state.total_purchases
    )
    dep_max = max(dependency['platform_dependency'], dependency['supplier_dependency'])
    days_to_liquidate = lock_data['days_to_liquidate']  # None = no sales velocity

    # 7. Grit Score: the same function on the baseline and on the stressed state.
    # Weights, multipliers and the short-runway cap are justified in grit.py.
    baseline_grit = grit.compute_grit(
        fragility['score'], baseline_runway_decay_estimate, dep_max, days_to_liquidate, bottom_line['runway_months']
    )
    scenario_grit = grit.compute_grit(
        stressed['score'], runway_decay_estimate, dep_max, days_to_liquidate, shock_results['runway']
    )

    return {
        "baseline": {**baseline, **bottom_line},
        "simulation": shock_results,
        "inventory": lock_data,
        "fragility": fragility,
        "dependency": dependency,
        "runway_decay_estimate": runway_decay_estimate,
        "baseline_runway_decay_estimate": baseline_runway_decay_estimate,
        "trajectory": trajectory,
        "grit_score": scenario_grit['score'],
        "baseline_grit": baseline_grit['score'],
        "grit_breakdown": scenario_grit,
        "ad_spend_ratio": ad_spend_ratio
    }

@app.post("/api/analyze")
def analyze_business(state: FullBusinessState):
    analysis = process_business_state(state)
    advice = llm_advisor.generate_strategic_advice(analysis)
    return {**analysis, "advice": advice}
@app.get("/api/mock")
def get_mock_business():
    return mock_data.generate_mock_business()

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    # Get full analyzed state for situational intelligence
    analysis = process_business_state(req.state)
    messages = [{"role": msg.role, "content": msg.content} for msg in req.messages]
    
    return StreamingResponse(
        llm_advisor.chat_with_advisor(messages, analysis),
        media_type="text/plain"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
