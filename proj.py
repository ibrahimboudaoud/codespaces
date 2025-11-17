import serial
import numpy as np
import pyaudio
import time

### --------------------------
### Serial connection
### --------------------------
SERIAL_PORT = "/dev/tty.usbserial-0001"   # CHANGE THIS
BAUD_RATE = 115200

ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
time.sleep(2)
print("Connected to EMG sensor...")

### --------------------------
### Audio system setup
### --------------------------
p = pyaudio.PyAudio()
volume = 0.5
sample_rate = 44100  
stream = p.open(format=pyaudio.paFloat32,
                channels=1,
                rate=sample_rate,
                output=True)

### --------------------------
### Helper: generate pure tone
### --------------------------
def generate_tone(freq, duration=0.05):
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(freq * t * 2 * np.pi)
    return tone.astype(np.float32)

### --------------------------
### EMG → Frequency Mapping
### --------------------------
MIN_FREQ = 200     # relaxed  
MAX_FREQ = 1200    # full flex

def map_emg_to_freq(emg):
    return MIN_FREQ + (emg / 1023.0) * (MAX_FREQ - MIN_FREQ)

### --------------------------
### Main Loop
### --------------------------
EMG_THRESHOLD = 60     # minimum activation to make sound

print("Reading EMG + generating sound...")

while True:
    try:
        line = ser.readline().decode().strip()
        if not line.isdigit():
            continue
        
        emg_value = int(line)

        if emg_value > EMG_THRESHOLD:
            freq = map_emg_to_freq(emg_value)
            tone = generate_tone(freq)
            stream.write(volume * tone)
        else:
            # Write silence
            stream.write(np.zeros(2048, dtype=np.float32))

    except KeyboardInterrupt:
        print("\nStopping...")
        break

### --------------------------
### Cleanup
### --------------------------
stream.stop_stream()
stream.close()
p.terminate()
ser.close()
