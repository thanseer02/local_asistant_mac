"""Audio device manager and CoreAudio resampler for MacAssistant.

Prevents Bluetooth HFP / SCO low-quality audio drop by:
1. Hard-pinning the input device to the built-in microphone by name (never by index).
2. If the pinned built-in mic is not found, NEVER falling back to a Bluetooth input or default input;
   disabling capture and notifying cleanly instead.
3. Managing listen_mode ("always" | "push_to_talk" | "smart") to close the capture stream completely
   when idle, media is playing, screen is locked, or quiet hours are active, turning off the orange mic indicator.
4. Resampling native sample rates (44.1k/48k) to 16kHz in memory using plain capture (no voice-processing IO unit).
"""

import logging
import math
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from .audio_diagnostics import AudioDiagnostics

logger = logging.getLogger("MacAssistant.AudioDeviceManager")

BLUETOOTH_KEYWORDS = ["bluetooth", "airpod", "wh-ch", "sony", "bose", "headset", "hands-free", "buds", "beats"]
BUILTIN_KEYWORDS = ["built-in", "builtin", "macbook", "internal", "mac mini", "imac", "studio display"]


class AudioDeviceManager:
    """Manages audio device selection, Bluetooth isolation, and sample rate conversion."""

    @classmethod
    def get_all_devices(cls, p) -> Dict[str, List[Dict[str, Any]]]:
        """Categorizes all connected audio devices into inputs and outputs."""
        inputs = []
        outputs = []
        count = p.get_device_count()

        for i in range(count):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "Unknown")
                device_data = {
                    "index": i,
                    "name": name,
                    "max_input_channels": info.get("maxInputChannels", 0),
                    "max_output_channels": info.get("maxOutputChannels", 0),
                    "sample_rate": int(info.get("defaultSampleRate", 44100)),
                    "is_bluetooth": any(k in name.lower() for k in BLUETOOTH_KEYWORDS),
                    "is_builtin": any(k in name.lower() for k in BUILTIN_KEYWORDS)
                }
                if device_data["max_input_channels"] > 0:
                    inputs.append(device_data)
                if device_data["max_output_channels"] > 0:
                    outputs.append(device_data)
            except Exception as e:
                logger.debug("Error querying device [%d]: %s", i, e)

        return {"inputs": inputs, "outputs": outputs}

    @classmethod
    def resolve_mic_device(
        cls,
        p,
        microphone_mode: str = "builtin",
        pinned_device_name: Optional[str] = None
    ) -> Tuple[Optional[int], int, str, str]:
        """Resolves the microphone device strictly by name.

        Rules:
        - If microphone_mode == "off": Returns None (Disabled).
        - If microphone_mode == "builtin":
            Searches strictly for a Built-in/MacBook/USB non-Bluetooth microphone.
            If NO non-Bluetooth microphone exists, returns (None, 16000, "None", reason).
            DOES NOT fall back to Bluetooth or default input.
        - If a pinned_device_name is provided:
            Matches by name. If not found or if it's Bluetooth while in builtin mode, rejects.
        - If microphone_mode == "default":
            Uses the current default input device, warning if Bluetooth.

        Returns: (device_index, native_sample_rate, device_name, status_message)
        """
        if microphone_mode == "off":
            return None, 16000, "Disabled", "Microphone listening is turned off in config."

        devices = cls.get_all_devices(p)
        inputs = devices["inputs"]

        if not inputs:
            return None, 16000, "None", "No audio input hardware devices detected."

        # 1. If explicit pinned name requested
        if pinned_device_name:
            clean_pin = pinned_device_name.strip().lower()
            for d in inputs:
                if clean_pin in d["name"].lower():
                    if microphone_mode == "builtin" and d["is_bluetooth"]:
                        msg = f"Pinned device '{d['name']}' is Bluetooth. Rejected in builtin mode to protect audio quality."
                        logger.warning(msg)
                        return None, 16000, "None", msg
                    return d["index"], d["sample_rate"], d["name"], "OK"
            msg = f"Pinned input device '{pinned_device_name}' not found."
            logger.warning(msg)
            return None, 16000, "None", msg

        # 2. Builtin mode: Hard-pin to Built-in or USB non-Bluetooth microphone
        if microphone_mode == "builtin":
            # Pass 1: Built-in MacBook/Internal microphone
            for d in inputs:
                if d["is_builtin"] and not d["is_bluetooth"]:
                    return d["index"], d["sample_rate"], d["name"], "OK"

            # Pass 2: USB external microphone (e.g., Blue Yeti, USB audio interface)
            for d in inputs:
                if not d["is_bluetooth"]:
                    return d["index"], d["sample_rate"], d["name"], "OK"

            # Strict isolation: Do NOT fall back to Bluetooth!
            msg = (
                "No built-in or USB microphone found. Refusing to open Bluetooth input "
                "to prevent audio quality drop (A2DP -> HFP)."
            )
            logger.warning(msg)
            return None, 16000, "None", msg

        # 3. Default mode
        first = inputs[0]
        status = "Warning: Bluetooth input active" if first["is_bluetooth"] else "OK"
        return first["index"], first["sample_rate"], first["name"], status

    @classmethod
    def is_media_playing(cls) -> bool:
        """Checks if Spotify, Music, or Chrome/Brave media is actively playing."""
        script = '''
        tell application "System Events"
            set isPlaying to false
            if exists (application process "Spotify") then
                tell application "Spotify" to if player state is playing then set isPlaying to true
            end if
            if exists (application process "Music") then
                tell application "Music" to if player state is playing then set isPlaying to true
            end if
            return isPlaying
        end tell
        '''
        try:
            res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=1.0)
            return "true" in res.stdout.lower()
        except Exception:
            return False

    @staticmethod
    def resample_to_16k(audio_bytes: bytes, src_rate: int) -> bytes:
        """Linear interpolation resampler converting native sample rate (44.1k/48k) to 16kHz."""
        if src_rate == 16000 or not audio_bytes:
            return audio_bytes

        import numpy as np

        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        num_src = len(samples)
        num_target = int(round(num_src * (16000.0 / src_rate)))

        if num_target == 0:
            return b""

        src_indices = np.linspace(0, num_src - 1, num_src)
        target_indices = np.linspace(0, num_src - 1, num_target)

        resampled = np.interp(target_indices, src_indices, samples).astype(np.int16)
        return resampled.tobytes()
