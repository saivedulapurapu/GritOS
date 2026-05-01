import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: No API KEY found in .env")
    exit(1)

genai.configure(api_key=api_key)

print("Starting Gemini 1.5 Test...")
try:
    # Attempting native system_instruction (Modern SDK)
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        system_instruction="You are a helpful business assistant."
    )
    response = model.generate_content("Say 'Gemini 1.5 is alive'")
    print(f"MODERN SUCCESS: {response.text}")
except Exception as e:
    print(f"MODERN FAILED: {e}")
    
    print("\nAttempting LEGACY history-based system instruction...")
    try:
        model_legacy = genai.GenerativeModel('gemini-1.5-flash')
        history = [
            {"role": "user", "parts": ["You are a helpful business assistant. Acknowledge."]},
            {"role": "model", "parts": ["Understood. I am ready."]}
        ]
        chat = model_legacy.start_chat(history=history)
        response_legacy = chat.send_message("Say 'Legacy mode is alive'")
        print(f"LEGACY SUCCESS: {response_legacy.text}")
    except Exception as e2:
        print(f"LEGACY FAILED: {e2}")
