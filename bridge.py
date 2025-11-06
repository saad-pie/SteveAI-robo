import serial
import time
import asyncio

# --- CONFIGURATION ---
# *** IMPORTANT: Change 'COMX' to your specific Bluetooth COM Port ***
BLUETOOTH_PORT = 'COMX' # <--- CHANGE THIS
BAUD_RATE = 9600 # Must match the Arduino code

class RoverBridge:
    """
    Manages the synchronous serial connection to the Arduino Rover.
    It uses asyncio.to_thread for blocking serial calls to keep the
    main event loop free.
    """
    def __init__(self):
        self.rover = None
        self.is_connected = False
        self.feedback_queue = asyncio.Queue()
        self._loop = asyncio.get_event_loop()
        self.connect()

    def connect(self):
        """Initializes the serial connection synchronously."""
        try:
            # 1. Open the Bluetooth/Serial connection
            self.rover = serial.Serial(BLUETOOTH_PORT, BAUD_RATE, timeout=0) # Non-blocking timeout
            time.sleep(2) # Give it a moment to connect and reset the Arduino
            self.is_connected = True
            print(f"✅ RoverBridge: Successfully connected to Rover on {BLUETOOTH_PORT}.")

        except serial.SerialException as e:
            print(f"❌ RoverBridge ERROR: Could not open port {BLUETOOTH_PORT}. Check pairing and port name.")
            print(e)
            self.is_connected = False

    def send_command_sync(self, command_char):
        """Sends a single character command to the Arduino (BLOCKING)."""
        if not self.is_connected:
            print(f"[RoverBridge] Not connected. Would have sent: '{command_char}'")
            return

        try:
            self.rover.write(command_char.encode()) # Commands must be sent as bytes
            print(f"[RoverBridge] -> Sent command: '{command_char}'")
        except Exception as e:
            print(f"[RoverBridge] Error sending command: {e}")

    async def send_command(self, command_char):
        """Sends a command using a separate thread (ASYNC)."""
        await self._loop.run_in_executor(
            None, # Use default executor (ThreadPoolExecutor)
            self.send_command_sync,
            command_char.upper()
        )

    async def listen_for_feedback(self):
        """Checks the buffer and puts any data from Arduino into the queue (ASYNC)."""
        if not self.is_connected:
            return

        # Use an asyncio.to_thread task to safely run the blocking readline loop
        await self._loop.run_in_executor(
            None,
            self._listen_for_feedback_sync
        )

    def _listen_for_feedback_sync(self):
        """The actual blocking loop to read serial data (SYNC)."""
        while self.is_connected:
            try:
                if self.rover.in_waiting > 0:
                    feedback = self.rover.readline().decode('utf-8').strip()
                    if feedback:
                        # Put feedback into the async queue for the AI script to process
                        self._loop.call_soon_threadsafe(self.feedback_queue.put_nowait, feedback)
                time.sleep(0.05) # Poll frequency
            except Exception as e:
                print(f"[RoverBridge] Error receiving data: {e}")
                break # Exit the loop on error

    async def get_feedback(self):
        """Async method to retrieve feedback from the queue."""
        return await self.feedback_queue.get()

    def close(self):
        """Closes the serial connection."""
        self.is_connected = False
        if self.rover and self.rover.is_open:
            self.rover.close()
            print("[RoverBridge] Serial connection closed.")

# --- EXAMPLE USAGE (for testing only) ---
if __name__ == "__main__":
    async def serial_test():
        bridge = RoverBridge()
        if not bridge.is_connected:
            return

        print("\n--- Running Bridge Test ---")
        await bridge.send_command('M') # Start Mission
        await asyncio.sleep(1)
        await bridge.send_command('F') # Forward
        await asyncio.sleep(2)
        await bridge.send_command('S') # Stop
        await asyncio.sleep(1)

        # Start listening for feedback in the background
        listener_task = asyncio.create_task(bridge.listen_for_feedback())

        # Check for feedback for a few seconds
        for _ in range(5):
            try:
                # Get feedback from the queue, with a timeout
                feedback = await asyncio.wait_for(bridge.get_feedback(), timeout=0.5)
                print(f"<- ROVER FEEDBACK (Test): {feedback}")
            except asyncio.TimeoutError:
                # No feedback in the last 0.5s
                pass

        listener_task.cancel()
        bridge.close()
        print("Test complete.")

    try:
        asyncio.run(serial_test())
    except KeyboardInterrupt:
        print("\nTest interrupted.")
