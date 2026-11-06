import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import capital_lock
import data_quality
import dependency_index
import financial_engine
import fragility_model
import grit
import llm_advisor
import mock_data
import runway_decay
import shock_engine
from schemas import CURRENCY_SYMBOLS, ChatRequest, FullBusinessState

logger = logging.getLogger("gritos")

app = FastAPI(title="GritOS Runway Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


@app.get("/")
async def health_check():
    return {"status": "online", "version": "2.0"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Never echo or log the request body: it may hold a business's private figures.
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    logger.info("Validation failed on %s: %d error(s)", request.url.path, len(errors))
    return JSONResponse(status_code=422, content={"detail": errors})


def process_business_state(state: FullBusinessState):
    # 1. Baseline calc
    baseline = financial_engine.calculate_operational_metrics(
        state.revenue, state.ad_spend, state.cogs, state.shipping_cost, state.rto_cost
    )
    bottom_line = financial_engine.calculate_net_metrics(baseline['contribution_margin'], state.fixed_costs, state.cash_in_bank)

    # 2. Shock Simulation
    shock_results = shock_engine.apply_shocks(
        state.dict(), state.cac_shock, state.rev_shock, state.cogs_shock, state.ad_spend_behaviour
    )

    # 3. Capital Lock
    lock_data = capital_lock.calculate_capital_lock(
        state.stock_units, state.cost_per_unit, state.daily_velocity, CURRENCY_SYMBOLS[state.currency]
    )

    # 4. Fragility tier (baseline structure) & shock sensitivity
    ad_spend_ratio = state.ad_spend / state.revenue if state.revenue > 0 else 0
    total_shock_pct = state.cac_shock + state.rev_shock + state.cogs_shock

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
        "currency": state.currency,
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
    analysis["data_quality"] = data_quality.build_report(state, analysis)
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
