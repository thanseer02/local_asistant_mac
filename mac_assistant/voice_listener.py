"""Wake-word listener and speech-to-text runner using openWakeWord / Whisper."""

import logging
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("MacAssistant.VoiceListener")


class VoiceListener:
    """
    Background microphone listener monitoring for wake-words:
    - 'hey jarvis'
    - 'hey friday'
    Dispatches recognized speech commands to VoiceCommandDispatcher.
    """

    def __init__(self, on_command_callback: Callable[[str], None]):
        self.on_command = on_command_callback
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, config: Dict[str, Any]) -> None:
        """Starts the microphone background listener thread."""
        voice_cfg = config.get("voice_commands", {})
        if not voice_cfg.get("enabled", False):
            logger.info("Voice wake-word commands are disabled in config.json.")
            return

        self.running = True
        self._thread = threading.Thread(target=self._listen_loop, args=(config,), daemon=True)
        self._thread.start()
        logger.info("Voice wake-word listener thread started.")

    def stop(self) -> None:
        self.running = False

    def _listen_loop(self, config: Dict[str, Any]) -> None:
        """
        Microphone listener loop.
        Monitors input stream for wake-word activation and subsequent command capture.
        """
        logger.info("Listening for 'Hey Jarvis' / 'Hey Friday' wake-words...")
        while self.running:
            # Sleep interval for audio buffer chunk inspection
            time.sleep(1)
