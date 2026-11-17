"""Voice synthesis and Marvel persona management."""

import logging
import os
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.VoiceEngine")

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class VoiceEngine:
    """Handles text formatting, persona management, and macOS speech synthesis."""

    def __init__(self):
        self._last_chosen_greeting: Optional[str] = None

    def get_active_persona(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves the active persona ('friday' or 'jarvis') from configuration."""
        persona_key = config.get("assistant_persona", "friday").lower()
        personas = config.get("personas", {})
        if persona_key in personas:
            return personas[persona_key]
        return {
            "voice": config.get("voice", "Moira"),
            "speech_rate": config.get("speech_rate", 175),
            "greetings": {}
        }

    def get_greeting(self, config: Dict[str, Any], hour: Optional[int] = None) -> str:
        """Constructs a time-aware, non-repeating greeting tailored to the persona."""
        if hour is None:
            hour = datetime.now().hour

        persona = self.get_active_persona(config)
        name = config.get("user_name", "Sir")
        greetings = persona.get("greetings", {})

        if 5 <= hour < 12:
            pool = greetings.get("morning", ["Good morning, {name}!"])
        elif 12 <= hour < 17:
            pool = greetings.get("afternoon", ["Good afternoon, {name}!"])
        elif 17 <= hour < 21:
            pool = greetings.get("evening", ["Good evening, {name}!"])
        else:
            pool = greetings.get("night", ["Working late, {name}?"])

        if isinstance(pool, list) and pool:
            candidates = [g for g in pool if g != self._last_chosen_greeting] or pool
            chosen = random.choice(candidates)
            self._last_chosen_greeting = chosen
            return chosen.format(name=name, title=name)
        elif isinstance(pool, str):
            return pool.format(name=name, title=name)

        return f"Welcome back, {name}!"

    def get_goodbye(self, config: Dict[str, Any]) -> str:
        """Constructs a polite shutdown/farewell message tailored to the persona."""
        persona = self.get_active_persona(config)
        name = config.get("user_name", "Sir")
        goodbyes = persona.get("goodbyes", [])

        if isinstance(goodbyes, list) and goodbyes:
            return random.choice(goodbyes).format(name=name, title=name)
        elif isinstance(goodbyes, str):
            return goodbyes.format(name=name, title=name)

        return f"Goodbye, {name}. Have a restful evening."

    def play_hud_chime(self, config: Dict[str, Any]) -> None:
        """Plays the Marvel HUD chime sound effect before speaking if enabled."""
        sound_cfg = config.get("hud_sound", {})
        if not sound_cfg.get("enabled", True):
            return

        sound_file = sound_cfg.get("sound_file", "hud_chime.wav")
        sound_path = SOUNDS_DIR / sound_file
        if sound_path.exists():
            try:
                # Play asynchronously and wait briefly for the crisp chime to trigger
                subprocess.run(["/usr/bin/afplay", str(sound_path)], check=False)
            except Exception as e:
                logger.debug("HUD chime audio playback error: %s", e)

    def speak(self, message: str, config: Dict[str, Any]) -> None:
        """Plays HUD chime (if enabled) and speaks via macOS say."""
        # 1. Play Marvel Iron Man HUD chime
        self.play_hud_chime(config)

        # 2. Synthesize speech
        persona = self.get_active_persona(config)
        voice = persona.get("voice", config.get("voice", "Moira"))
        rate = str(persona.get("speech_rate", config.get("speech_rate", 175)))

        logger.info("Speaking with voice '%s' (rate %s): %s", voice, rate, message)
        subprocess.run(["/usr/bin/say", "-v", voice, "-r", rate, message], check=False)
