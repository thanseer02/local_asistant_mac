"""Push-to-talk voice controller using native macOS on-device recording & speech recognition."""

import logging
from pathlib import Path
import subprocess
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("MacAssistant.PushToTalk")

HELPER_BIN = Path(__file__).resolve().parent / "mac_voice_helper_bin"
SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class PushToTalkController:
    """Manages push-to-talk audio capture and recognition.

    Guarantees:
    - Audio input opens ONLY on trigger and terminates immediately after utterance.
    - Zero continuous background capture, preventing Bluetooth headphones from dropping to HFP.
    - Uses native macOS on-device Speech framework (requiresOnDeviceRecognition=true).
    """

    def __init__(self, on_command_callback: Optional[Callable[[str], None]] = None):
        self.on_command = on_command_callback
        self._is_recording = False
        self._lock = threading.Lock()

    @staticmethod
    def play_cue(sound_name: str = "hud_chime.wav") -> None:
        """Plays short audio cue for start/stop of voice input."""
        p = SOUNDS_DIR / sound_name
        if p.exists():
            try:
                subprocess.Popen(["/usr/bin/afplay", str(p)])
            except Exception:
                pass

    def trigger_recording_async(self, duration: float = 4.0) -> None:
        """Triggers push-to-talk capture asynchronously in a background thread."""
        with self._lock:
            if self._is_recording:
                logger.debug("Push-to-talk already in progress.")
                return
            self._is_recording = True

        threading.Thread(
            target=self._record_and_transcribe,
            args=(duration,),
            name="MacAssistant-PTTWorker",
            daemon=True
        ).start()

    def _record_and_transcribe(self, duration: float) -> None:
        try:
            logger.info("Push-to-talk started (capturing for %.1fs)...", duration)
            self.play_cue("hud_chime.wav")

            if not HELPER_BIN.exists():
                logger.warning("Native voice helper binary not found at %s", HELPER_BIN)
                return

            res = subprocess.run(
                [str(HELPER_BIN), str(duration)],
                capture_output=True,
                text=True,
                timeout=duration + 5.0
            )

            # Play closing audio cue
            self.play_cue("hud_chime.wav")

            transcript = res.stdout.strip()
            logger.info("Push-to-talk transcript received: '%s'", transcript)

            if transcript and self.on_command:
                self.on_command(transcript)

        except Exception as e:
            logger.error("Error during push-to-talk recording: %s", e)
        finally:
            with self._lock:
                self._is_recording = False
            logger.info("Push-to-talk capture stream completely closed. Bluetooth output preserved.")
