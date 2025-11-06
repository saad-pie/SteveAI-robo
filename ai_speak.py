#!/usr/bin/env python

import sys
import os
from gtts import gTTS
from openai import OpenAI
from langdetect import detect, DetectorFactory, LangDetectException

# Ensures consistent results for langdetect
DetectorFactory.seed = 0

# --- 1. Get User Input and Filename ---
# Usage: python ai_speak.py "Your question here" [output_filename.mp3]
if len(sys.argv) < 2:
    print("Usage: python ai_speak.py \"Your question here\" [output_filename.mp3]")
    sys.exit(1)

# The question is everything after the script name, up to the last argument if it's not the output file
user_input_args = sys.argv[1:]
output_filename = "ai_response.mp3"

# Check if the last argument is a filename (ends in .mp3)
if len(user_input_args) > 1 and user_input_args[-1].endswith(".mp3"):
    output_filename = user_input_args[-1]
    user_input = " ".join(user_input_args[:-1])
else:
    user_input = " ".join(user_input_args)

print(f"User Query: {user_input}")

# --- 2. Call OpenAI API ---
try:
    client = OpenAI(
        api_key="ddc-a4f-93af1cce14774a6f831d244f4df3eb9e",
        base_url="https://api.a4f.co/v1"
    )

    print("Requesting AI response...")

    response = client.chat.completions.create(
        model="provider-5/gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Keep your response concise, educational, and under 40 words. You may respond in the language of the user's question."},
            {"role": "user", "content": user_input}
        ],
        temperature=0.7,
        max_tokens=50,
        stream=False
    )

    # Extract the AI's text response
    ai_response_text = response.choices[0].message.content
    print("\n--- AI Response Text ---")
    print(ai_response_text)
    print("------------------------")

    # --- 3. Language Detection ---
    detected_lang = 'en' # Default to English
    try:
        detected_lang = detect(ai_response_text)
        print(f"Language Detected: {detected_lang}")
    except LangDetectException:
        print(f"Warning: Could not reliably detect language. Defaulting to '{detected_lang}'.")
    except Exception as e:
        print(f"Warning: Language detection failed with error: {e}. Defaulting to '{detected_lang}'.")

    # --- 4. Convert Text to Speech (gTTS) ---
    tts = gTTS(text=ai_response_text, lang=detected_lang)
    tts.save(output_filename)
    
    # --- 5. Confirmation ---
    print(f"\n✅ Success! The audio file was generated in language '{detected_lang}'.")
    
except Exception as e:
    print(f"\n❌ An error occurred during API or file generation: {e}")
    # Cleanup file on error
    if 'output_filename' in locals() and os.path.exists(output_filename):
        os.remove(output_filename)
    sys.exit(1) # Exit with an error code if the API/generation failed

