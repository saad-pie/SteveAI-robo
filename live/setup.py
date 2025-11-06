# python
import google.genai
import pillow  # Check for pillow
import pyaudio # Check for pyaudio

print("--- Successfully imported all target libraries! ---")
print(f"Google GenAI SDK version: {google.genai.__version__}")
# Note: Pydantic is likely imported internally by google.genai

# --- Configuration ---
# You need to set your API key as an environment variable in Termux:
# export GEMINI_API_KEY="YOUR_API_KEY_HERE"
# You should restart Termux or open a new session after setting the variable.

try:
    client = google.genai.Client()
    print("Client initialized successfully.")
except Exception as e:
    print(f"Error initializing client (check API Key and environment): {e}")

