#!/usr/bin/env python3
"""Inspect all audio input devices and find working device index."""

import sys

try:
    import pyaudio
except ImportError:
    print("pyaudio is not installed.")
    sys.exit(1)

p = pyaudio.PyAudio()
count = p.get_device_count()
print("=" * 60)
print(f"Total Audio Devices Found: {count}")
print("=" * 60)

inputs = []
for i in range(count):
    info = p.get_device_info_by_index(i)
    if info.get("maxInputChannels", 0) > 0:
        inputs.append((i, info["name"], int(info["defaultSampleRate"])))
        print(f"[{i}] Input Device: {info['name']}")
        print(f"    Channels: {info['maxInputChannels']}, Default Rate: {int(info['defaultSampleRate'])} Hz\n")

if not inputs:
    print("❌ No input devices found.")
    sys.exit(1)

# Test opening stream on each detected input device
print("-" * 60)
print("Testing opening audio stream on devices...")
working_index = None

for idx, name, rate in inputs:
    print(f"Testing device [{idx}] '{name}' at {rate}Hz...")
    try:
        s = p.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, input_device_index=idx, frames_per_buffer=1024)
        data = s.read(1024, exception_on_overflow=False)
        s.stop_stream()
        s.close()
        print(f"  ✅ SUCCESS: Device [{idx}] can record audio!")
        working_index = idx
        break
    except Exception as e:
        print(f"  ❌ Failed: {e}")

p.terminate()

if working_index is not None:
    print("=" * 60)
    print(f"🎉 Working device identified at index: {working_index}")
    print("=" * 60)
