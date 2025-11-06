import os
import asyncio
import io
import traceback
import pyaudio

# --- NEW: Import the RoverBridge from bridge.py ---
from bridge import RoverBridge

from google import genai
from google.genai import types
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

# --- AI Tool Configuration for Rover Control ---

ROVER_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="send_rover_command",
            description="Sends a single character command to the Arduino-controlled rover for movement (F=Forward, B=Backward, L=Left, R=Right, S=Stop), mission control (M=Start Mission, X=Stop Mission). Only call this function.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "command_char": types.Schema(
                        type=types.Type.STRING,
                        description="The single character command (e.g., 'F' for forward, 'S' for stop)."
                    )
                },
                required=["command_char"]
            )
        )
    ]
)


# --- Configuration for Live Connect Session ---

VAD_CONFIG = types.RealtimeInputConfig(
    automatic_activity_detection=AutomaticActivityDetection(
        end_of_speech_sensitivity=EndSensitivity.END_SENSITIVITY_LOW
    )
)

CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    media_resolution="MEDIA_RESOLUTION_MEDIUM",

    # System Instruction: Tell the model to use the tool
    system_instruction="You are a voice controller for a mobile rover. Your task is to listen to the user and ONLY use the `send_rover_command` tool to control the rover. Do not interject or speak proactively. If the user asks you to move, use the tool. If the user asks a general question, you can answer it without the tool.",

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
    tools=[ROVER_TOOL], # Use the tool defined above
)

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self, bridge: RoverBridge):
        self.bridge = bridge # The external RoverBridge instance
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

        print("\n--- Listening to Microphone. Say a command! ---")

        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data})

    async def handle_tool_call(self, tool_call):
        """Processes a tool call from the model (e.g., 'send_rover_command')."""
        if tool_call.function_call.name == "send_rover_command":
            args = dict(tool_call.function_call.args)
            command_char = args.get("command_char")

            if command_char and isinstance(command_char, str) and len(command_char) == 1:
                # Execute the serial command via the injected bridge object
                await self.bridge.send_command(command_char)

                # Send the response back to the model
                response = types.ToolResponse(
                    function_response=types.FunctionResponse(
                        name="send_rover_command",
                        response={"status": "Command sent successfully.", "command": command_char.upper()}
                    )
                )
                await self.session.send_tool_response(response)
            else:
                print(f"[TOOL] Invalid command_char received: {command_char}")
                response = types.ToolResponse(
                    function_response=types.FunctionResponse(
                        name="send_rover_command",
                        response={"error": "Invalid command character format."}
                    )
                )
                await self.session.send_tool_response(response)

    async def process_rover_feedback(self):
        """Retrieves and prints feedback from the bridge's queue."""
        if not self.bridge.is_connected:
            return

        while True:
            # Wait for feedback to appear in the queue
            feedback = await self.bridge.get_feedback()
            print(f"\n<- ROVER FEEDBACK: {feedback}")


    async def receive_audio_and_process(self):
        "Reads from the session, processes text/tools, and writes pcm chunks to the play queue"
        while True:
            turn = self.session.receive()
            async for response in turn:
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(f"USER: {text}", end="\r", flush=True)
                    continue
                if tool_call := response.tool_call:
                    print(f"\nAI requested tool: {tool_call.function_call.name}")
                    await self.handle_tool_call(tool_call)
                    continue

            # Stop playback on turn_complete
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
            print("\nAI Response Complete. Ready for next command.")

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
                tg.create_task(self.receive_audio_and_process())
                tg.create_task(self.play_audio())
                
                # Start the background task to listen for Arduino feedback
                if self.bridge.is_connected:
                    tg.create_task(self.bridge.listen_for_feedback())
                    tg.create_task(self.process_rover_feedback())

                await send_text_task
                raise asyncio.CancelledError("User requested exit (or 'q' was typed)")

        except asyncio.CancelledError:
            print("\nExiting chat loop.")
        except ExceptionGroup as EG:
            traceback.print_exception(EG)
        except Exception as e:
            print(f"\nConnection Error during runtime: {e}")
        finally:
            if self.audio_stream:
                 await asyncio.to_thread(self.audio_stream.close)
            if 'pya' in globals():
                await asyncio.to_thread(pya.terminate)
            print("AI Cleanup complete.")


if __name__ == "__main__":
    # 1. Initialize the Bridge (synchronous call)
    rover_bridge = RoverBridge()
    
    # 2. Initialize the AI Loop with the Bridge
    main = AudioLoop(bridge=rover_bridge)
    
    try:
        # 3. Run the main async loop
        asyncio.run(main.run())
    except KeyboardInterrupt:
        print("\nSession interrupted by user (Ctrl+C).")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        # 4. Ensure the serial port is closed on exit
        rover_bridge.close()
        print("Rover Bridge cleanup complete.")
