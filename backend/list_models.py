import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

print("Listing available Groq models...")
if not api_key:
    print("FAILED TO LIST: GROQ_API_KEY not found.")
    exit(1)

client = Groq(api_key=api_key)

try:
    models = client.models.list()
    for m in models.data:
        print(f"- {m.id}")
except Exception as e:
    print(f"FAILED TO LIST: {e}")
