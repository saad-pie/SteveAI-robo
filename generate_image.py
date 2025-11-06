import os
import sys
import time
import json
import requests
from io import BytesIO
from PIL import Image
from openai import OpenAI
from deep_translator import GoogleTranslator

# --- CONFIGURATION & VALIDATION ---
if len(sys.argv) < 2:
    print("❌ Error: No prompt provided.")
    print("Usage: python generate_image.py \"Your desired image prompt here\"")
    sys.exit(1)

prompt = sys.argv[1]
timestamp = int(time.time())

# Define the standard save directory for Termux
save_dir = os.path.expanduser("~/storage/pictures")
os.makedirs(save_dir, exist_ok=True) 

save_path_final = os.path.join(save_dir, f"blended_image_final_{timestamp}.png")
save_path_intermediate = os.path.join(save_dir, f"phoenix_base_image_{timestamp}.png")

# --- OPENAI CLIENT SETUP ---
A4F_API_KEY = "ddc-a4f-d61cbe09b0f945ea93403a420dba8155" 
A4F_BASE_URL = "https://api.a4f.co/v1"
client = OpenAI(api_key=A4F_API_KEY, base_url=A4F_BASE_URL)

# --- MODEL IDs ---
# FIX: Use the correct Imagen 4 ID
IMAGEN_MODEL_ID = "provider-4/imagen-4"
PHOENIX_MODEL_ID = "provider-4/phoenix"
# FIX: Use the correct GPT-4o Mini ID for vision support
VISION_MODEL_ID = "provider-5/gpt-4o-mini-2024-07-18" 
REFINER_MODEL_ID = "provider-5/gpt-4o-mini" # Retained original for refinement since it works for text


# --- HELPER FUNCTIONS ---

def refine_prompt(current_prompt):
    """
    Refines the prompt. FIX: Switched to plain text response parsing due to JSON error.
    """
    print(f"\n--- 🧠 Prompt Refinement ---")
    print(f"Original Prompt: '{current_prompt}'")
    
    system_instruction = (
        "You are an expert AI image generation prompt engineer. Your response MUST be a JSON object "
        "with exactly two keys: 'primary_prompt' (the highly detailed prompt) and 'negative_prompt' (a comma-separated string of negative keywords). "
        "Generate a primary prompt that includes: 1. Subject/Scene details. 2. Lighting/Mood. 3. Artistic Style/Medium. 4. Camera/Aesthetic terms. "
        "Example Response: {'primary_prompt': 'A detailed scene...', 'negative_prompt': 'blurry, noise, watermark'}"
    )
    
    # We will still ask for JSON but parse it as a string to handle API quirks
    try:
        completion = client.chat.completions.create(
            model=REFINER_MODEL_ID,
            # Removed response_format={"type": "json_object"} to fix "Expecting value" error
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Refine this into a perfect image prompt: {current_prompt}"},
            ],
            temperature=0.8,
        )
        
        # Manually parse the text content, assuming it adheres to the requested JSON format
        json_string = completion.choices[0].message.content.strip()
        refined_json = json.loads(json_string)
        
        refined_prompt = refined_json.get("primary_prompt", current_prompt)
        # Note: The system instruction was changed to ask for a comma-separated STRING for negative_prompt
        negative_prompt_string = refined_json.get("negative_prompt", "")
        
        if not negative_prompt_string:
             negative_prompt_string = "blurry, worst quality, noise, disfigured, watermark, ugly"
        
        print("\n✅ Refined Prompt:", refined_prompt)
        print("🚫 Negative Prompt:", negative_prompt_string)
        
        return {
            "prompt": refined_prompt,
            "negative_prompt": negative_prompt_string
        }
        
    except Exception as error:
        print(f"❌ Error getting chat completion: {error}. Falling back to original prompt.")
        return {
            "prompt": current_prompt,
            "negative_prompt": "blurry, worst quality, noise, disfigured, watermark, ugly"
        }

# (translate_prompt function remains unchanged)
def translate_prompt(p):
    """Translates the prompt to English using Google Translator."""
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(p)
        if translated.strip().lower() == p.strip().lower():
            print("Prompt already in English. Skipping translation.")
            return p
        else:
            print(f"Translated prompt: {translated}")
            return translated
    except Exception as e:
        print(f"Translation failed: {e}. Using original prompt.")
        return p


# --- MAIN EXECUTION ---
refined_output = refine_prompt(prompt)
refined_prompt_text = refined_output["prompt"]
negative_prompt_text = refined_output["negative_prompt"]
PromptEN = translate_prompt(refined_prompt_text)

image_url_phoenix = None
phoenix_description = refined_prompt_text # Fallback description

# --- STEP 1: Generate with Phoenix for Base Composition ---
try:
    print("\n--- 1️⃣ Phoenix Base Composition ---")
    
    # Negative prompt applied using the system-style string format
    phoenix_prompt_final = f"negative things NOT to generate: {negative_prompt_text}. {PromptEN}"

    response_phoenix = client.images.generate(
        prompt=phoenix_prompt_final,
        model=PHOENIX_MODEL_ID, 
        n=1,
        size="1024x1024",
    )

    if response_phoenix.data and response_phoenix.data[0].url:
        image_url_phoenix = response_phoenix.data[0].url
        print(f"Phoenix Image URL: {image_url_phoenix}")

        # Download and save the intermediate image
        img_response = requests.get(image_url_phoenix)
        img_response.raise_for_status()
        
        with open(save_path_intermediate, 'wb') as handler:
            handler.write(img_response.content)
        print(f"Intermediate Phoenix image saved to {save_path_intermediate}")
    else:
        print("❌ Phoenix image generation failed. Cannot proceed.")
        sys.exit(1)

except Exception as e:
    print(f"❌ An error occurred during Phoenix generation: {e}")
    sys.exit(1)


# --- STEP 2: Describe Phoenix Output using Vision Model ---
try:
    print("\n--- 2️⃣ Vision Model Analysis (Describing Phoenix Output) ---")
    
    # FIX: Use the correct VISION_MODEL_ID
    vision_response = client.chat.completions.create(
      model=VISION_MODEL_ID,
      messages=[
        {
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": f"Based on the following image, generate a highly detailed, descriptive text prompt (max 200 words) that accurately captures its composition, lighting, and mood. The goal is to recreate this exact scene but with a photorealistic, cinematic style."
            },
            {
              "type": "image_url",
              "image_url": {
                "url": image_url_phoenix
              }
            }
          ]
        }
      ]
    )
    
    phoenix_description = vision_response.choices[0].message.content
    print("✨ Vision Model Description:", phoenix_description)

except Exception as e:
    print(f"❌ Error using Vision Model to describe image: {e}. Using refined text prompt as fallback.")
    # Fallback remains: phoenix_description = refined_prompt_text


# --- STEP 3: Refine with Imagen 4 (Text Blending) ---
try:
    print("\n--- 3️⃣ Imagen 4 Style Refinement (The Blend) ---")
    
    # Blend the Phoenix description (composition) with the Imagen 4 style guide
    final_prompt_base = f"Transform this scene: '{phoenix_description}' into an ultra-photorealistic image with the signature detail and volumetric lighting of Imagen 4. Maintain the exact composition, focus on clarity and cinematic depth."

    # Negative prompt applied using the system-style string format
    imagen4_prompt_final = f"negative things NOT to generate: {negative_prompt_text}. {final_prompt_base}"
    
    response_imagen4 = client.images.generate(
        prompt=imagen4_prompt_final, 
        # FIX: Use the correct IMAGEN_MODEL_ID
        model=IMAGEN_MODEL_ID, 
        n=1,
        size="1024x1024",
    )

    if response_imagen4.data and response_imagen4.data[0].url:
        image_url_final = response_imagen4.data[0].url
        print(f"Final (Blended) Image URL: {image_url_final}")

        # --- DOWNLOAD AND SAVE FINAL IMAGE ---
        print(f"Downloading final image from URL...")
        final_img_response = requests.get(image_url_final)
        final_img_response.raise_for_status()

        # Save the final image locally
        with open(save_path_final, 'wb') as handler:
            handler.write(final_img_response.content)

        print(f"\n✨ **SUCCESS!** Blended image saved to {save_path_final}")
        
        # Confirm download properties
        img = Image.open(BytesIO(final_img_response.content))
        print(f"File properties: {img.width}x{img.height}, format: {img.format}")

    else:
        print("❌ Imagen 4 refinement failed. No final image data received.")
        
except Exception as e:
    print(f"❌ An error occurred during Imagen 4 generation: {e}")
