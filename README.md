# SteveAI-robo

The official repository for **SteveAI-robo**, a command-line-driven AI assistant and interface designed for seamless interaction via voice, text, and generative AI.

This project combines Speech-to-Text (STT), Text-to-Speech (TTS), and image generation capabilities, with a focus on real-time and semi-real-time performance, suggesting its potential use in robotics or interactive AI systems.

## ✨ Features

* **🎙️ Voice Command Processing:** Convert spoken input to text for command execution (`ai_transcribe.py`).
* **🗣️ Text-to-Speech Output:** Respond to user commands with synthesized speech (`ai_speak.py` and `speak.sh`).
* **🖼️ AI Image Generation:** Generate creative images based on provided prompts (`generate_image.py`).
* **🔗 Modular System Architecture:** A central "bridge" module for managing API calls and component communication (`bridge.py`).
* **⏱️ Real-time Interaction:** Dedicated modules for live and semi-live AI processing (in the `live/` directory).

## 🚀 Getting Started

These instructions will get a copy of the project up and running on your local machine.

### Prerequisites

* Python 3.x
* Git
* Required Python libraries (e.g., specific AI/ML libraries, API clients).

You will need to install dependencies. A `requirements.txt` file is highly recommended for this.

```bash
# Example: Install dependencies (if you add a requirements.txt file)
pip install -r requirements.txt
