"""Speech output service wrapping macOS /usr/bin/say with natural cadence and HUD audio cues."""

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.SpeechOutput")

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class SpeechOutputService:
    """Manages audio speech synthesis via macOS /usr/bin/say with human-like phrasing."""

    def __init__(self, sounds_dir: Optional[Path] = None):
        self.sounds_dir = sounds_dir or SOUNDS_DIR

    @staticmethod
    def naturalize_text(text: str) -> str:
        """
        Transforms raw text into a conversational cadence:
        - Cleans markdown, URLs, symbols, bullet dashes
        - Injects natural micro-pauses after greetings (Sir, Boss)
        - Replaces technical abbreviations with spoken words
        """
        if not text:
            return ""

        # Remove URLs
        t = re.sub(r"https?://\S+", "", text)
        # Strip markdown styling characters
        t = re.sub(r"[*_#`~\[\]]", "", t)
        # Turn bullet points into spoken pauses
        t = re.sub(r"\n\s*[-*•]\s*", ", ", t)
        # Add a subtle pause after salutations
        t = re.sub(r"^(Sir|Boss),\s*", r"\1... ", t)
        # Replace °C with degrees
        t = t.replace("°C", " degrees")
        t = t.replace("°F", " degrees")
        # Normalize repeated punctuation and whitespace
        t = re.sub(r",\s*,+", ",", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def play_hud_chime(self, sound_file: str = "hud_chime.wav") -> None:
        """Plays the sci-fi HUD chime sound effect via afplay."""
        sound_path = self.sounds_dir / sound_file
        if sound_path.exists():
            try:
                subprocess.run(["/usr/bin/afplay", str(sound_path)], check=False, timeout=2)
            except Exception as e:
                logger.debug("HUD audio playback error: %s", e)

    def speak(self, text: str, voice: str = "Moira", rate: int = 168, play_chime: bool = True) -> None:
        """
        Executes macOS /usr/bin/say using natural cadence and safe arguments.
        """
        if not text:
            return

        speech_ready_text = self.naturalize_text(text)

        if play_chime:
            self.play_hud_chime()

        logger.info("Speaking with voice '%s' (rate %d): %s", voice, rate, speech_ready_text)
        try:
            # Safe argument list - never shell=True
            subprocess.run(
                ["/usr/bin/say", "-v", str(voice), "-r", str(rate), speech_ready_text],
                check=False,
                timeout=25
            )
        except Exception as e:
            logger.error("Failed executing speech synthesis: %s", e)
