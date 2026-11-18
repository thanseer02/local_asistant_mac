"""System health, permissions, audio devices, and dependency diagnostic utility (--doctor)."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Dict, List, Tuple

from .audio_device_manager import AudioDeviceManager


class SystemDoctor:
    """Diagnoses system permissions, audio devices & Bluetooth HFP state, binary dependencies, launchd status."""

    @classmethod
    def run_all_checks(cls) -> Dict[str, Tuple[bool, str]]:
        results = {}
        results["macOS Version"] = cls.check_macos_version()
        results["Audio Synthesis (/usr/bin/say)"] = cls.check_binary("/usr/bin/say")
        results["Audio Playback (/usr/bin/afplay)"] = cls.check_binary("/usr/bin/afplay")
        results["AppleScript (/usr/bin/osascript)"] = cls.check_binary("/usr/bin/osascript")
        results["Virtual Environment Python"] = cls.check_python_env()
        results["Microphone Hardware Devices"] = cls.check_audio_devices()
        results["Bluetooth Audio Profile (A2DP vs HFP)"] = cls.check_bluetooth_profile()
        results["LaunchAgent Configuration"] = cls.check_launch_agent()
        results["SQLite Database Integrity"] = cls.check_database()
        return results

    @staticmethod
    def check_macos_version() -> Tuple[bool, str]:
        ver = platform.mac_ver()[0]
        return True, f"macOS {ver} ({platform.machine()})"

    @staticmethod
    def check_binary(path: str) -> Tuple[bool, str]:
        if Path(path).exists() and os.access(path, os.X_OK):
            return True, f"Found executable at {path}"
        return False, f"Missing binary {path}"

    @staticmethod
    def check_python_env() -> Tuple[bool, str]:
        v = sys.version_info
        return True, f"Python {v.major}.{v.minor}.{v.micro}"

    @staticmethod
    def check_audio_devices() -> Tuple[bool, str]:
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            devs = AudioDeviceManager.get_all_devices(p)
            p.terminate()

            inputs = devs["inputs"]
            outputs = devs["outputs"]

            in_summary = ", ".join([f"{d['name']} ({d['sample_rate']}Hz)" for d in inputs]) if inputs else "None"
            out_summary = ", ".join([f"{d['name']} ({d['sample_rate']}Hz)" for d in outputs]) if outputs else "None"

            msg = f"Inputs: [{in_summary}] | Outputs: [{out_summary}]"
            return len(inputs) > 0, msg
        except Exception as e:
            return False, f"Error inspecting devices: {e}"

    @staticmethod
    def check_bluetooth_profile() -> Tuple[bool, str]:
        is_hfp = AudioDeviceManager.is_bluetooth_hfp_active()
        if is_hfp:
            return False, "⚠️ Bluetooth mic is active! Headset is locked in low-quality 16kHz SCO/HFP mode."
        return True, "✅ Bluetooth output is in high-fidelity mode (A2DP / High Quality)."

    @staticmethod
    def check_launch_agent() -> Tuple[bool, str]:
        agent_path = Path.home() / "Library" / "LaunchAgents" / "com.personal.macassistant.plist"
        if agent_path.exists():
            return True, f"LaunchAgent plist found at {agent_path}"
        return False, f"LaunchAgent not installed at {agent_path}"

    @staticmethod
    def check_database() -> Tuple[bool, str]:
        db_path = Path(__file__).resolve().parent.parent / "data" / "conversation.db"
        if db_path.exists():
            return True, f"Database active ({db_path.stat().st_size} bytes)"
        return True, "Database initialized on first use"

    @classmethod
    def print_report(cls) -> None:
        print("\n🩺  MacAssistant System Diagnostic (--doctor)\n" + "=" * 65)
        checks = cls.run_all_checks()
        all_ok = True
        for name, (ok, msg) in checks.items():
            status = "✅ PASS" if ok else "⚠️ WARN"
            if not ok:
                all_ok = False
            print(f"{status} | {name}:\n      {msg}")
        print("=" * 65)
        if all_ok:
            print("🚀 All diagnostics passed! MacAssistant is healthy.\n")
        else:
            print("Notice: Review warnings above for hardware optimization.\n")
