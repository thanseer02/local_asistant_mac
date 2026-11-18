#!/usr/bin/env python3
"""Step 1 & Step 2 Diagnostic Script: Environment, Permissions, and Audio."""

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.config_manager import ConfigManager
from mac_assistant.audio_device_manager import AudioDeviceManager
from mac_assistant.audio_diagnostics import AudioDiagnostics


def run_diagnostics():
    print("=" * 70)
    print("DIAGNOSTIC STEP 1 & 2: Environment, Permissions & Audio Inspection")
    print("=" * 70)

    # 1. Python & OS
    print(f"Python Executable: {sys.executable}")
    print(f"Python Version:    {sys.version}")
    print(f"macOS Version:     {platform.mac_ver()[0]} ({platform.machine()})")

    # 2. Config validation
    cfg = ConfigManager.load()
    print("\n--- Config Keys Audit ---")
    print(f"assistant_persona: {cfg.get('assistant_persona')}")
    print(f"user_name:         {cfg.get('user_name')}")
    print(f"microphone_mode:   {cfg.get('microphone_mode')}")
    print(f"voice_commands:    {cfg.get('voice_commands', {}).get('enabled')}")

    # 3. Audio Devices Inspection
    print("\n--- Audio Devices ---")
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        devs = AudioDeviceManager.get_all_devices(p)
        print(f"Total Inputs Found:  {len(devs['inputs'])}")
        for d in devs["inputs"]:
            print(f"  [Input] #{d['index']} {d['name']} | Rate: {d['sample_rate']}Hz | Built-in: {d['is_builtin']} | Bluetooth: {d['is_bluetooth']}")
        print(f"Total Outputs Found: {len(devs['outputs'])}")
        for d in devs["outputs"]:
            print(f"  [Output] #{d['index']} {d['name']} | Rate: {d['sample_rate']}Hz | Built-in: {d['is_builtin']} | Bluetooth: {d['is_bluetooth']}")
        p.terminate()
    except Exception as e:
        print(f"Error querying PyAudio: {e}")

    # 4. Bluetooth Profile
    print("\n--- Bluetooth Audio Profile Status ---")
    hfp_active, hfp_msg = AudioDiagnostics.is_bluetooth_hfp_active()
    print(f"HFP Active: {hfp_active}")
    print(f"Status:     {hfp_msg}")

    # 5. Microphone Recording RMS Test (5 seconds)
    print("\n--- 5-Second Mic Audio RMS / Peak Test ---")
    try:
        import pyaudio
        import numpy as np

        p = pyaudio.PyAudio()
        # Find default or first input
        dev_idx = None
        for i in range(p.get_device_count()):
            if p.get_device_info_by_index(i).get("maxInputChannels", 0) > 0:
                dev_idx = i
                break

        if dev_idx is not None:
            info = p.get_device_info_by_index(dev_idx)
            rate = int(info.get("defaultSampleRate", 16000))
            name = info.get("name")
            print(f"Testing input device [{dev_idx}] '{name}' at {rate}Hz...")

            stream = p.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, input_device_index=dev_idx, frames_per_buffer=1024)
            chunks = []
            start = time.time()
            while time.time() - start < 3.0:
                data = stream.read(1024, exception_on_overflow=False)
                chunks.append(data)
            stream.stop_stream()
            stream.close()

            raw = b"".join(chunks)
            samples = np.frombuffer(raw, dtype=np.int16)
            rms = np.sqrt(np.mean(samples.astype(float)**2))
            peak = np.max(np.abs(samples))
            print(f"Captured {len(samples)} samples:")
            print(f"  RMS Energy: {rms:.1f}")
            print(f"  Peak Level: {peak}")
            if rms < 10.0:
                print("  ⚠️ Audio signal is near silent/dead.")
            elif peak >= 32700:
                print("  ⚠️ Audio signal is clipping.")
            else:
                print("  ✅ Audio signal has healthy dynamic range.")
        else:
            print("  ❌ No input device to test.")
        p.terminate()
    except Exception as e:
        print(f"Mic test error: {e}")

    print("=" * 70)


if __name__ == "__main__":
    run_diagnostics()
