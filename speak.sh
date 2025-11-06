#!/bin/bash

# Check if user provided input
if [ -z "$1" ]; then
    echo "Usage: ./speak.sh \"Your question here\""
    exit 1
fi

# 1. Clean up the input text to create a safe, short filename.
# Get the first 4 words of the user input
INPUT_TEXT="$@"
FILENAME_PREFIX=$(echo "$INPUT_TEXT" | awk '{print $1"_"$2"_"$3"_"$4}' | tr -d '[:punct:]' | tr ' ' '_' | tr '[:upper:]' '[:lower:]')

# Ensure the prefix is not empty and append a timestamp (or just keep it simple)
if [ -z "$FILENAME_PREFIX" ]; then
    FILENAME_PREFIX="speech_$(date +%s)"
fi

OUTPUT_FILE="${FILENAME_PREFIX}.mp3"
TARGET_DIR="storage/documents"

echo "--- Starting AI Voice Generation ---"
echo "Target Filename: ${OUTPUT_FILE}"

# 2. Execute the Python script with the question and the new filename
# This is where ai_speak.py detects the language internally.
python ai_speak.py "$INPUT_TEXT" "$OUTPUT_FILE"

# Check the exit status of the Python script (0 means success)
if [ $? -eq 0 ]; then
    # 3. Move the file if the Python script succeeded
    if [ -f "$OUTPUT_FILE" ]; then
        mkdir -p "$TARGET_DIR" # Ensure the target directory exists
        mv "$OUTPUT_FILE" "$TARGET_DIR/"
        echo "--- COMPLETE ---"
        echo "File moved to: ${TARGET_DIR}/${OUTPUT_FILE}"
    else
        echo "Error: Python script finished, but output file (${OUTPUT_FILE}) was not found."
    fi
else
    echo "--- FAILED ---"
    echo "The Python script encountered an error. Check its output for details."
fi
