import os
import asyncio
import io
import traceback
import pyaudio

from google import genai
from google.genai import types
# --- EXPLICIT IMPORTS FOR CLARITY ---
from google.genai.types import (
    AutomaticActivityDetection, EndSensitivity, Blob
)

# --- Configuration Constants ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.5-flash-native-audio-preview-09-2025" 

DEFAULT_MODE = "none"

# Initialize Client
client = genai.Client(
    http_options={"api_version": "v1beta"},
    api_key=os.environ.get("GEMINI_API_KEY"),
)

tools = [
    types.Tool(google_search=types.GoogleSearch()),
    types.Tool(
        function_declarations=[
        ]
    ),
]

# --- VAD SENSITIVITY CONFIG (Confirmed Working Constant Name) ---
VAD_CONFIG = types.RealtimeInputConfig(
    automatic_activity_detection=AutomaticActivityDetection(
        # This constant name is confirmed correct. Low sensitivity helps ignore background noise.
        end_of_speech_sensitivity=EndSensitivity.END_SENSITIVITY_LOW 
    )
)

# --- FINAL CONFIGURATION ---
CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    media_resolution="MEDIA_RESOLUTION_MEDIUM",
    
    # --- FIX: Use System Instruction to disable Proactive Speech ---
    # This tells the model to wait for a full user turn before responding.
    system_instruction="You are a helpful voice assistant. Wait for the user to finish speaking before providing a response. Do not interject or speak proactively.",

    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Orus")
        )
    ),
    realtime_input_config=VAD_CONFIG,
    
    context_window_compression=types.ContextWindowCompressionConfig(
        trigger_tokens=32000,
        sliding_window=types.SlidingWindow(target_tokens=32000),
    ),
    tools=tools,
)

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None
        self.audio_stream = None

    async def send_text(self):
        while True:
            text = await asyncio.to_thread(
                input,
                "message > ",
            )
            if text.lower() == "q":
                break
            await self.session.send(input=text or ".", end_of_turn=True)

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            audio_blob = Blob(
                data=msg["data"], 
                mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}"
            )
            await self.session.send_realtime_input(audio=audio_blob)
            self.out_queue.task_done()

    async def listen_audio(self):
        try:
            mic_info = pya.get_default_input_device_info()
            mic_index = mic_info.get("index")
        except:
            print("Warning: Could not get default mic info. Using default index 0.")
            mic_index = 0
            
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=CHUNK_SIZE,
        )
        kwargs = {"exception_on_overflow": False}

        print("\n--- Listening to Microphone. Say something after the prompt! ---")

        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data})

    async def receive_audio(self):
        "Reads from the session, prints text transcription, and writes pcm chunks to the play queue"
        while True:
            turn = self.session.receive()
            async for response in turn:
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(text, end="", flush=True) 

            # Stop playback on turn_complete
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
            print() 

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            await asyncio.to_thread(stream.write, bytestream)
            self.audio_in_queue.task_done()

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session
                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                send_text_task = tg.create_task(self.send_text())
                tg.create_task(self.send_realtime()) 
                tg.create_task(self.listen_audio())  
                tg.create_task(self.receive_audio()) 
                tg.create_task(self.play_audio())    

                await send_text_task
                raise asyncio.CancelledError("User requested exit (or 'q' was typed)")

        except asyncio.CancelledError:
            print("\nExiting chat loop.")
        except ExceptionGroup as EG:
            traceback.print_exception(EG)
        except Exception as e:
            # We specifically catch the connection error here for better feedback
            print(f"\nConnection Error during runtime: {e}")
        finally:
            if self.audio_stream:
                 await asyncio.to_thread(self.audio_stream.close)
            # The client should be terminated last
            if 'pya' in globals():
                await asyncio.to_thread(pya.terminate)
            print("Cleanup complete.")


if __name__ == "__main__":
    main = AudioLoop(video_mode=DEFAULT_MODE)
    try:
        asyncio.run(main.run())
    except KeyboardInterrupt:
        print("\nSession interrupted by user (Ctrl+C).")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

