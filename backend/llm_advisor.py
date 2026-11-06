"""
Optional LLM layer: strategy bullets and chat via Groq-hosted LLaMA models.

Everything works without GROQ_API_KEY: the dashboard falls back to fixed bullets and
the chat replies with a clear "not configured" message. The model is given the
computed metrics; it does not compute anything itself.
"""
import logging
import os

import groq
from dotenv import load_dotenv

logger = logging.getLogger("gritos.llm")

load_dotenv()
_api_key = os.getenv("GROQ_API_KEY")
client = groq.Groq(api_key=_api_key) if _api_key else None

# Tried in order; a rate limit or unknown model moves on to the next one
MODEL_CASCADE = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

FALLBACK_ADVICE = ["⚠️ Optimize contribution margins.", "🛡️ Enhance cash reserves.", "🚀 Scale organic acquisition."]
NO_KEY_MESSAGE = "⚠️ Groq API key not configured. Set GROQ_API_KEY in backend/.env to enable the AI advisor."
CAPACITY_ERRORS = (groq.RateLimitError, groq.NotFoundError)

# Dashboard bullets cached per (Grit, estimate) bucket to save quota for chat
_advice_cache = {}


def generate_strategic_advice(metrics):
    """Three short strategy bullets for the dashboard (cached)."""
    cache_key = f"{round(metrics.get('grit_score', 0))}_{round(metrics.get('runway_decay_estimate', 0) * 10)}"
    if cache_key in _advice_cache:
        return _advice_cache[cache_key]
    if client is None:
        return list(FALLBACK_ADVICE)

    try:
        response = client.chat.completions.create(
            model=MODEL_CASCADE[0],
            messages=[
                {"role": "system", "content": "You are the GritOS Strategy Engine. Give 3 short D2C strategy bullets."},
                {"role": "user", "content": f"Grit: {metrics.get('grit_score')}, "
                                            f"6-month runway-decay estimate: {metrics.get('runway_decay_estimate')}%."},
            ],
            temperature=0.7,
            max_tokens=150,
            timeout=10,
        )
    except groq.APIError as e:
        logger.warning("Advice generation failed (%s); using fallback bullets", type(e).__name__)
        return list(FALLBACK_ADVICE)

    text = response.choices[0].message.content or ""
    bullets = [line.strip().lstrip("- ") for line in text.split("\n") if line.strip()][:3]
    _advice_cache[cache_key] = bullets
    return bullets


def _system_prompt(metrics):
    runway = metrics.get("baseline", {}).get("runway_months", "Unknown")
    if runway is None:
        runway_text = "No cash burn (runway unlimited)"
    elif runway == "Unknown":
        runway_text = "Unknown"
    else:
        runway_text = f"{runway} months"
    return f"""
    IDENTITY: GritOS AI Strategy Engine.
    CONTEXT: You are inside GritOS, a financial risk and scenario analytics tool.
    STATUS:
    - Grit Score: {metrics.get('grit_score')}
    - 6-month Runway-Decay Estimate (heuristic, not a fitted survival model): {metrics.get('runway_decay_estimate', 0)}%
    - Cash Runway: {runway_text}.

    BEHAVIOR:
    1. Professional and specific.
    2. Do NOT provide generic advice. Be specific to the Grit Score and runway-decay estimate.
    3. If Grit Score is low, be urgent and focused on capital preservation.
    4. If the runway-decay estimate is high, suggest growth or optimization.
    5. End with a brief, relevant follow-up question.
    6. Use markdown for structure (bold, lists, tables) but keep it short.
    """


def chat_with_advisor(messages, metrics):
    """Streaming chat. Yields text chunks."""
    if not messages:
        yield "⚠️ No message received. Please type a question."
        return
    if client is None:
        yield NO_KEY_MESSAGE
        return

    groq_messages = [{"role": "system", "content": _system_prompt(metrics)}]
    for msg in messages[:-1]:
        role = "assistant" if msg["role"] in ("model", "assistant") else "user"  # Groq expects 'assistant'
        groq_messages.append({"role": role, "content": msg["content"]})
    groq_messages.append({"role": "user", "content": messages[-1]["content"]})

    last_error = "no model available"
    for model_name in MODEL_CASCADE:
        try:
            stream = client.chat.completions.create(
                model=model_name, messages=groq_messages, stream=True, temperature=0.7,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
            return
        except CAPACITY_ERRORS as e:
            last_error = type(e).__name__
            logger.info("Model %s unavailable (%s); trying next", model_name, last_error)
            continue
        except groq.APIError as e:
            logger.warning("Chat failed on %s (%s)", model_name, type(e).__name__)
            yield f"⚠️ AI advisor unavailable ({type(e).__name__}). The analysis above is unaffected."
            return

    yield f"⚠️ All AI models are at capacity right now ({last_error}). Please try again shortly."
