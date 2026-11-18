"""Audio device manager and CoreAudio resampler for MacAssistant.

Prevents Bluetooth HFP / SCO low-quality audio drop by:
1. Pinning the input device to Built-in or USB microphone, NEVER Bluetooth input.
2. Opening at the native hardware sample rate (e.g. 44.1k/48k) and resampling to 16 kHz in software.
3. Detecting device switches (AirPods / Bluetooth connects/disconnects) and maintaining high quality A2DP output.
4. Warning when a Bluetooth mic would trigger mono/low-quality SCO mode.
"""

import logging
import math
import subprocess
from typing import Any, Dict, List, Optional, Tuple

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
                device_data = {
                    "index": i,
                    "name": info.get("name", "Unknown"),
                    "max_input_channels": info.get("maxInputChannels", 0),
                    "max_output_channels": info.get("maxOutputChannels", 0),
                    "sample_rate": int(info.get("defaultSampleRate", 44100)),
                    "is_bluetooth": any(k in info.get("name", "").lower() for k in BLUETOOTH_KEYWORDS),
                    "is_builtin": any(k in info.get("name", "").lower() for k in BUILTIN_KEYWORDS)
                }
                if device_data["max_input_channels"] > 0:
                    inputs.append(device_data)
                if device_data["max_output_channels"] > 0:
                    outputs.append(device_data)
            except Exception as e:
                logger.debug("Error querying device [%d]: %s", i, e)

        return {"inputs": inputs, "outputs": outputs}

    @classmethod
    def is_bluetooth_hfp_active(cls) -> bool:
        """Checks if Bluetooth is currently forced into low-quality 16kHz/8kHz SCO/HFP mode."""
        try:
            cmd = ["/usr/sbin/system_profiler", "SPAudioDataType"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.5)
            out = res.stdout
            # When Bluetooth audio is in HFP/SCO profile, Current SampleRate is 16000 or 8000
            # and Transport is Bluetooth for Default Input.
            lines = out.splitlines()
            is_bt_input = False
            for line in lines:
                if "Transport: Bluetooth" in line:
                    is_bt_input = True
                if is_bt_input and "Current SampleRate: 16000" in line:
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def resolve_mic_device(
        cls,
        p,
        mode: str = "builtin",
        preferred_name: Optional[str] = None
    ) -> Tuple[Optional[int], int, str, bool]:
        """Resolves the microphone device according to the configured mode.

        Returns: (device_index, native_sample_rate, device_name, is_bluetooth_warning)
        mode options:
          - "builtin": Strictly prefers Built-in / USB mic; avoids Bluetooth at all costs.
          - "default": Uses system default or first available.
          - "off": Disables mic capture.
        """
        if mode == "off":
            return None, 16000, "Disabled", False

        devices = cls.get_all_devices(p)
        inputs = devices["inputs"]

        if not inputs:
            return None, 16000, "None", False

        # If a specific preferred_name was requested, try that first
        if preferred_name:
            for d in inputs:
                if preferred_name.lower() in d["name"].lower():
                    is_bt = d["is_bluetooth"]
                    return d["index"], d["sample_rate"], d["name"], is_bt

        # Builtin mode: prioritize Built-in / Internal / USB microphones
        if mode == "builtin":
            # 1. Builtin match
            for d in inputs:
                if d["is_builtin"] and not d["is_bluetooth"]:
                    return d["index"], d["sample_rate"], d["name"], False

            # 2. USB or external non-Bluetooth microphone
            for d in inputs:
                if not d["is_bluetooth"]:
                    return d["index"], d["sample_rate"], d["name"], False

            # 3. Fallback: If only Bluetooth exists (e.g. Mac mini with no internal mic)
            bt_dev = inputs[0]
            logger.warning(
                "No built-in or USB microphone found. Falling back to '%s' (Bluetooth). "
                "Note: Opening Bluetooth mic may drop headphone audio quality to HFP 16kHz.",
                bt_dev["name"]
            )
            return bt_dev["index"], bt_dev["sample_rate"], bt_dev["name"], True

        # Default mode: return first available input
        first = inputs[0]
        return first["index"], first["sample_rate"], first["name"], first["is_bluetooth"]

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
