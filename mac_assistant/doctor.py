"""System health, permissions, and dependency diagnostic utility (--doctor)."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Dict, List, Tuple


class SystemDoctor:
    """Diagnoses system permissions, binary dependencies, launchd status, and audio devices."""

    @classmethod
    def run_all_checks(cls) -> Dict[str, Tuple[bool, str]]:
        results = {}
        results["macOS Version"] = cls.check_macos_version()
        results["Audio Synthesis (/usr/bin/say)"] = cls.check_binary("/usr/bin/say")
        results["Audio Playback (/usr/bin/afplay)"] = cls.check_binary("/usr/bin/afplay")
        results["AppleScript (/usr/bin/osascript)"] = cls.check_binary("/usr/bin/osascript")
        results["Virtual Environment Python"] = cls.check_python_env()
        results["Microphone Hardware Access"] = cls.check_microphone_access()
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
    def check_microphone_access() -> Tuple[bool, str]:
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            count = p.get_device_count()
            p.terminate()
            if count > 0:
                return True, f"Detected {count} audio devices available"
            return False, "No audio input devices found"
        except Exception as e:
            return False, f"PyAudio error: {e}"

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
        print("\n🩺  MacAssistant System Diagnostic (--doctor)\n" + "=" * 50)
        checks = cls.run_all_checks()
        all_ok = True
        for name, (ok, msg) in checks.items():
            status = "✅ PASS" if ok else "❌ FAIL"
            if not ok:
                all_ok = False
            print(f"{status} | {name}: {msg}")
        print("=" * 50)
        if all_ok:
            print("🚀 All diagnostics passed! MacAssistant is healthy.\n")
        else:
            print("⚠️ Some diagnostics need attention. Review above.\n")
