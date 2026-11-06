from llm_advisor import chat_with_advisor

# Simple test harness
messages = [{"role": "user", "content": "hello"}]
# runway_decay_estimate is a percentage (0-100), same as the API returns
metrics = {"grit_score": 85, "runway_decay_estimate": 60.7, "baseline": {"runway_months": 12}, "dependency": {"platform_dependency": 20, "supplier_dependency": 10}}

print("Testing chat_with_advisor...")
try:
    # We want to see the error that triggers the except block in llm_advisor.py
    # but llm_advisor.py HAS an except block that silences it.
    # Let's temporarily modify it or just trust the print there.
    # chat_with_advisor streams: join the chunks to see the full reply
    response = "".join(chat_with_advisor(messages, metrics))
    print(f"RESPONSE: {response}")
except Exception as e:
    print(f"TOP LEVEL ERROR: {e}")
