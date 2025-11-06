import serial
import time

# --- CONFIGURATION ---
# *** IMPORTANT: Change 'COMX' to your specific Bluetooth COM Port (e.g., 'COM8') ***
BLUETOOTH_PORT = 'COMX' 
BAUD_RATE = 9600 # Must match the Arduino code's Serial.begin(9600)

try:
    # 1. Open the Bluetooth/Serial connection
    rover = serial.Serial(BLUETOOTH_PORT, BAUD_RATE, timeout=1)
    time.sleep(2) # Give it a moment to connect and reset the Arduino
    print(f"Successfully connected to Rover on {BLUETOOTH_PORT}.")
    
except serial.SerialException as e:
    print(f"ERROR: Could not open port {BLUETOOTH_PORT}. Check pairing and port name.")
    print(e)
    exit()

def send_command(command_char):
    """Sends a single character command to the Arduino."""
    try:
        rover.write(command_char.encode()) # Commands must be sent as bytes
        print(f"-> Sent command: '{command_char}'")
    except Exception as e:
        print(f"Error sending command: {e}")

def listen_for_feedback():
    """Checks the buffer and prints any data sent from the Arduino."""
    try:
        if rover.in_waiting > 0:
            # Read all available data and decode it
            feedback = rover.readline().decode('utf-8').strip()
            if feedback:
                print(f"<- ROVER FEEDBACK: {feedback}")
            return feedback
    except Exception as e:
        print(f"Error receiving data: {e}")
    return None

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    
    # 1. Your AI/CLI script decides to start the mission
    send_command('M') 
    time.sleep(1)
    
    # 2. Loop to keep the mission running and check for alerts
    while True:
        alert = listen_for_feedback()
        
        # Example: If the 'FIRE DETECTED' alert is received, stop the mission
        if "FIRE DETECTED" in alert:
            send_command('X') # Send the Mission Stop command
            break
        
        # This is where your other Python scripts could run:
        # For example, if you wanted the robot to *speak* the alert:
        # if "ALERT" in alert:
        #     # Run your text-to-speech script!
        #     subprocess.run(['python', 'ai_speak.py', alert])
            
        time.sleep(0.5) # Don't flood the system
        
