import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

load_dotenv()  # .env in backend/ or the repo root (see .env.example)

import data_quality
import db
import edgar_api
import llm_advisor
import mock_data
import repository
from pipeline import process_business_state
from schemas import ChatRequest, FullBusinessState

logger = logging.getLogger("gritos")

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = FastAPI(title="GritOS Runway Intelligence API", lifespan=lifespan)
app.include_router(edgar_api.router)

DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def allowed_origins():
    """Comma-separated ALLOWED_ORIGINS env var; never '*'. No cookies are used, so no credentials."""
    raw = os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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


@app.post("/api/analyze")
def analyze_business(state: FullBusinessState, session=Depends(db.get_db)):
    analysis = process_business_state(state)
    analysis["data_quality"] = data_quality.build_report(state, analysis)
    scenario_id = repository.save_analysis(session, state, analysis, state.business_name,
                                           extra_inputs=repository.list_inputs(state))
    advice = llm_advisor.generate_strategic_advice(analysis)
    return {**analysis, "advice": advice, "scenario_id": scenario_id}


@app.get("/api/history")
def history(limit: int = Query(50, ge=1, le=500), business: str | None = None, session=Depends(db.get_db)):
    return repository.list_history(session, limit=limit, business=business)


@app.get("/api/scenarios/{scenario_id}")
def scenario_detail(scenario_id: int, session=Depends(db.get_db)):
    found = repository.get_scenario(session, scenario_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return found


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
