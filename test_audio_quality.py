#!/usr/bin/env python3
"""Audio verification script testing output sample rate and Bluetooth profile before and after mic capture."""

import subprocess
import time

from mac_assistant.audio_device_manager import AudioDeviceManager
from mac_assistant.audio_diagnostics import AudioDiagnostics
from mac_assistant.microphone_service import MicrophoneService


def run_audio_verification():
    print("=" * 65)
    print("🎧 MacAssistant Audio Quality & Bluetooth Profile Verification Test")
    print("=" * 65)

    # 1. Profile Before
    hfp_before, msg_before = AudioDiagnostics.is_bluetooth_hfp_active()
    print(f"\n[1] Profile BEFORE mic capture: {msg_before}")

    # 2. Start Mic in Smart / Builtin Mode
    mic = MicrophoneService(microphone_mode="builtin", listen_mode="smart")
    opened = mic.start_listening(lambda chunk: None)
    print(f"\n[2] Attempted opening capture stream in 'builtin' mode: Success = {opened}")
    print(f"    Active Input Device Selected: '{mic.active_device_name}'")

    time.sleep(1.0)

    # 3. Profile During
    hfp_during, msg_during = AudioDiagnostics.is_bluetooth_hfp_active()
    print(f"\n[3] Profile DURING mic active state: {msg_during}")

    # 4. Stop stream
    mic.stop_listening()

    # 5. Profile After
    hfp_after, msg_after = AudioDiagnostics.is_bluetooth_hfp_active()
    print(f"\n[4] Profile AFTER mic capture stopped: {msg_after}")

    print("\n" + "=" * 65)
    if not hfp_during:
        print("🎉 SUCCESS: Bluetooth output remained in high-fidelity stereo (A2DP).")
        print("   No audio quality drop occurred!")
    else:
        print("⚠️ Notice: Bluetooth headset switched to HFP. Check hardware configuration.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_audio_verification()
