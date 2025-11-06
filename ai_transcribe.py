#!/usr/bin/env python

import sys
import os
from openai import OpenAI

# --- Configuration ---
API_KEY = "ddc-a4f-93af1cce14774a6f831d244f4df3eb9e"
BASE_URL = "https://api.a4f.co/v1"
MODEL = "provider-5/whisper-1"
AUDIO_DIR = "storage/documents"

def transcribe_audio(audio_filename):
    """
    Handles API call to transcribe the given audio file.
    """
    
    # 1. Construct full path and check file existence
    full_path = os.path.join(AUDIO_DIR, audio_filename)
    
    if not os.path.exists(full_path):
        print(f"❌ Error: Audio file not found at {full_path}")
        print(f"Please ensure '{audio_filename}' is in the '{AUDIO_DIR}' directory.")
        return

    print(f"--- Starting Transcription of: {audio_filename} ---")
    print(f"Model: {MODEL}")

    # 2. Initialize the OpenAI client
    try:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    except Exception as e:
        print(f"❌ Error initializing OpenAI client: {e}")
        return

    # 3. Call the transcription API
    try:
        # The 'audio.transcriptions.create' method handles the file upload automatically
        with open(full_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=MODEL,
                file=audio_file
            )

        # 4. Extract and print the transcribed text
        transcribed_text = response.text
        
        print("\n✅ Transcription Complete:")
        print("---------------------------------")
        print(transcribed_text)
        print("---------------------------------")

    except Exception as e:
        print(f"❌ An error occurred during transcription: {e}")
        # Check if the error is related to API key or file format
        if "Authentication" in str(e):
            print("Hint: Check your API Key.")
        elif "Unsupported file type" in str(e):
            print("Hint: Ensure the audio file format is supported (e.g., mp3, wav, m4a).")


# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ai_transcribe.py <audio_filename>")
        print("Example: python ai_transcribe.py hola.mp3")
        sys.exit(1)
        
    # The filename is the first argument after the script name
    filename_to_transcribe = sys.argv[1]
    transcribe_audio(filename_to_transcribe)
