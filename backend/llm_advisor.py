import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

# Global cache for dashboard bullets to preserve quota for chat
_advice_cache = {}

# Model cascade: fast/cheap to large/capable
MODEL_CASCADE = [
    'llama-3.3-70b-versatile',
    'llama-3.1-8b-instant',
]

def get_working_model(system_instruction=None):
    """Try each model in cascade order, return first working one."""
    if not client:
        return None
    for model_name in MODEL_CASCADE:
        try:
            # We don't initialize a class instance like Gemini, just verify models exist or do a tiny test
            # But with Groq it's better to just try it at generation time.
            return model_name
        except Exception:
            continue
    return None

def generate_strategic_advice(metrics):
    """Dashboard static bullets with heavy caching."""
    cache_key = f"{round(metrics.get('grit_score', 0))}_{round(metrics.get('survival_prob', 0)*10)}"
    if cache_key in _advice_cache:
        return _advice_cache[cache_key]

    if not client:
        return ["⚠️ Optimize contribution margins.", "🛡️ Enhance cash reserves.", "🚀 Scale organic acquisition."]

    try:
        sys_prompt = "You are the GritOS Strategy Engine. Give 3 short D2C strategy bullets."
        prompt = f"Grit: {metrics.get('grit_score')}, Survival: {metrics.get('survival_prob')}."
        
        response = client.chat.completions.create(
            model=MODEL_CASCADE[0],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150,
            timeout=10
        )
        res_text = response.choices[0].message.content
        res = [l.strip().lstrip('- ') for l in res_text.split('\n') if l.strip()][:3]
        _advice_cache[cache_key] = res
        return res
    except Exception as e:
        print(f"Advice Gen Error: {e}")
        return ["⚠️ Optimize contribution margins.", "🛡️ Enhance cash reserves.", "🚀 Scale organic acquisition."]

def handle_local_interactive(msg):
    """
    Retired local handlers to ensure full AI intelligence for every query.
    """
    return None

def chat_with_advisor(messages, metrics):
    """Interactive Streaming Chat with Situational Intelligence using Groq."""
    if not messages:
        yield "⚠️ No message received. Please type a question."
        return

    if not client:
        yield "⚠️ Groq API key not configured."
        return

    latest = messages[-1]["content"]

    runway = metrics.get('baseline', {}).get('runway_months', 'Unknown')
    if runway is None:
        runway_text = "No cash burn (runway unlimited)"
    elif runway == 'Unknown':
        runway_text = "Unknown"
    else:
        runway_text = f"{runway} months"
    
    sys = f"""
    IDENTITY: GritOS AI Strategy Engine.
    CONTEXT: You are inside GritOS, a high-end resilience platform.
    STATUS:
    - Grit Score: {metrics.get('grit_score')}
    - Survival Probability: {metrics.get('survival_prob', 0)}%
    - Cash Runway: {runway_text}.
    
    BEHAVIOR:
    1. Professional, elite, and predictive.
    2. Do NOT provide generic advice. Be specific to the Grit Score and survival state.
    3. If Grit Score is low, be urgent and focused on capital preservation.
    4. If Survival is high, suggest aggressive growth or optimization.
    5. Always be interactive—end with a brief, relevant follow-up question.
    6. Use markdown for structure (bold, lists, tables) but keep it punchy.
    """
    
    # Format messages for Groq (OpenAI compatible)
    groq_messages = [{"role": "system", "content": sys}]
    for msg in messages[:-1]:
        # Groq expects 'assistant' instead of 'model'
        role = "assistant" if msg["role"] == "model" else "user"
        groq_messages.append({"role": role, "content": msg["content"]})
        
    groq_messages.append({"role": "user", "content": latest})

    # Try each model in cascade
    last_error = "All models unavailable. Please check your API quota or connection."
    for model_name in MODEL_CASCADE:
        try:
            stream = client.chat.completions.create(
                model=model_name,
                messages=groq_messages,
                stream=True,
                temperature=0.7,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
            return  # Success — stop trying other models
        except Exception as e:
            err_str = str(e)
            if '429' in err_str or '404' in err_str or 'rate' in err_str.lower():
                last_error = err_str
                continue  # Try next model
            else:
                # Non-quota error, report immediately
                yield f"⚠️ Strategic Link Interrupted: {err_str[:120]}."
                return

    # All models exhausted
    yield f"⚠️ All AI engines are temporarily at capacity via Groq. {last_error}"
