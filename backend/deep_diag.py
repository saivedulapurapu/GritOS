import os
from groq import Groq
from dotenv import load_dotenv
import traceback

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

print("Starting Deep Diagnostic for Groq...")
if not api_key:
    print("❌ Error: GROQ_API_KEY not found.")
    exit(1)

client = Groq(api_key=api_key)

try:
    # Try with a very safe model name and NO system_instruction first
    model_name = 'llama-3.1-8b-instant' # Universal fallback
    print(f"Testing {model_name}...")
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=20
    )
    print(f"SUCCESS: {response.choices[0].message.content}")
except Exception:
    traceback.print_exc()

print("\nTesting llama-3.3-70b-versatile with system_instruction...")
try:
    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hi"}
        ],
        max_tokens=20
    )
    print(f"SUCCESS 70b: {response.choices[0].message.content}")
except Exception:
    traceback.print_exc()
