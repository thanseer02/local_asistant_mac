#!/usr/bin/env python3
"""Live microphone monitor to test speech detection in real time."""

import math
import struct
import sys
import time

try:
    import pyaudio
except ImportError:
    print("pyaudio is not installed.")
    sys.exit(1)

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

p = pyaudio.PyAudio()
stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

print("=" * 60)
print("🎙️ Real-time Microphone Level Test")
print("Device: Sony WH-CH510 Connected")
print("Speak into your headphones mic now. Watch the audio bar:")
print("=" * 60)

try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        shorts = struct.unpack(f"{CHUNK}h", data)
        sum_squares = sum(s * s for s in shorts)
        rms = int(math.sqrt(sum_squares / CHUNK))
        
        # Visual meter
        bars = "#" * min(int(rms / 50), 40)
        status = ">>> WAKE TRIGGERED! <<<" if rms > 600 else ""
        print(f"\rLevel: {rms:5d} | {bars:<40} {status}", end="", flush=True)
except KeyboardInterrupt:
    print("\nTest finished.")
finally:
    stream.stop_stream()
    stream.close()
    p.terminate()
