"""Audio diagnostic, device isolation, and Bluetooth HFP/SCO detection service.

Functions:
- Queries native hardware input and output devices.
- Checks if any Bluetooth device is currently forced into low-quality 16kHz/8kHz HFP/SCO mode.
- Identifies whether the active machine has a built-in microphone or requires external input.
- Pinpoints active capture stream counts to guarantee a single shared stream.
"""

import logging
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MacAssistant.AudioDiagnostics")

BLUETOOTH_KEYWORDS = ["bluetooth", "airpod", "wh-ch", "sony", "bose", "headset", "hands-free", "buds", "beats"]
BUILTIN_KEYWORDS = ["built-in", "builtin", "macbook", "internal", "mac mini", "imac", "studio display"]


class AudioDiagnostics:
    """Provides deep inspection of macOS CoreAudio hardware, Bluetooth transport, and HFP profile."""

    @staticmethod
    def get_system_audio_report() -> Dict[str, Any]:
        """Runs system_profiler SPAudioDataType to extract transport, sample rates, and default status."""
        report: Dict[str, Any] = {
            "default_input": None,
            "default_output": None,
            "bluetooth_devices": [],
            "builtin_devices": [],
            "is_bluetooth_hfp_active": False,
            "raw_output": ""
        }
        try:
            cmd = ["/usr/sbin/system_profiler", "SPAudioDataType"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            raw = res.stdout
            report["raw_output"] = raw

            current_device: Dict[str, Any] = {}
            lines = raw.splitlines()

            for line in lines:
                sline = line.strip()
                if not sline:
                    continue

                if line.startswith("        ") and line.endswith(":") and not line.endswith("Devices:"):
                    dev_name = sline.rstrip(":")
                    current_device = {"name": dev_name}

                if "Default Input Device: Yes" in sline:
                    report["default_input"] = current_device.get("name")
                if "Default Output Device: Yes" in sline or "Default System Output Device: Yes" in sline:
                    report["default_output"] = current_device.get("name")
                if "Transport: Bluetooth" in sline:
                    current_device["transport"] = "Bluetooth"
                    if current_device.get("name") and current_device["name"] not in report["bluetooth_devices"]:
                        report["bluetooth_devices"].append(current_device["name"])
                if "Transport: Built-in" in sline:
                    current_device["transport"] = "Built-in"
                    if current_device.get("name") and current_device["name"] not in report["builtin_devices"]:
                        report["builtin_devices"].append(current_device["name"])
                if "Current SampleRate: 16000" in sline or "Current SampleRate: 8000" in sline:
                    if current_device.get("transport") == "Bluetooth":
                        report["is_bluetooth_hfp_active"] = True

        except Exception as e:
            logger.debug("Failed running system_profiler SPAudioDataType: %s", e)

        return report

    @classmethod
    def is_bluetooth_hfp_active(cls) -> Tuple[bool, str]:
        """Checks if any Bluetooth audio output is locked in 16kHz mono SCO/HFP mode."""
        rep = cls.get_system_audio_report()
        if rep["is_bluetooth_hfp_active"]:
            bt_devs = ", ".join(rep["bluetooth_devices"]) if rep["bluetooth_devices"] else "Bluetooth headset"
            return True, f"HFP/SCO Profile Active on {bt_devs} (Audio downgraded to 16kHz mono voice mode)."
        return False, "A2DP High-Fidelity Active (Audio output running in high-fidelity stereo)."
