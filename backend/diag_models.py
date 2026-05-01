import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('GROQ_API_KEY')
client = Groq(api_key=api_key) if api_key else None

test_models = [
    'llama-3.3-70b-versatile',
    'llama-3.1-8b-instant',
]

print("Starting specific model diagnostic for Groq...")
if not client:
    print("❌ Error: GROQ_API_KEY not found.")
    exit(1)

for m_name in test_models:
    try:
        print(f"Testing {m_name}...", end=" ")
        response = client.chat.completions.create(
            model=m_name,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
            timeout=5
        )
        print(f"✅ OK")
    except Exception as e:
        print(f"❌ Error: {str(e)[:100]}...")

print("Diagnostic complete.")
