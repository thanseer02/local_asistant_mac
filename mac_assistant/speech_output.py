"""Speech output service wrapping macOS /usr/bin/say with volume safety and HUD audio cues."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.SpeechOutput")

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class SpeechOutputService:
    """Manages audio speech synthesis via macOS /usr/bin/say and UI chimes."""

    def __init__(self, sounds_dir: Optional[Path] = None):
        self.sounds_dir = sounds_dir or SOUNDS_DIR

    def play_hud_chime(self, sound_file: str = "hud_chime.wav") -> None:
        """Plays the sci-fi HUD chime sound effect via afplay."""
        sound_path = self.sounds_dir / sound_file
        if sound_path.exists():
            try:
                subprocess.run(["/usr/bin/afplay", str(sound_path)], check=False, timeout=2)
            except Exception as e:
                logger.debug("HUD audio playback error: %s", e)

    def speak(self, text: str, voice: str = "Moira", rate: int = 172, play_chime: bool = True) -> None:
        """
        Executes macOS /usr/bin/say using safe argument lists.
        """
        if not text:
            return

        if play_chime:
            self.play_hud_chime()

        logger.info("Speaking with voice '%s' (rate %d): %s", voice, rate, text)
        try:
            # Safe argument list - never shell=True
            subprocess.run(
                ["/usr/bin/say", "-v", str(voice), "-r", str(rate), text],
                check=False,
                timeout=20
            )
        except Exception as e:
            logger.error("Failed executing speech synthesis: %s", e)
