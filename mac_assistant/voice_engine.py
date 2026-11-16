"""Voice synthesis and Marvel persona management."""

import logging
import random
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.VoiceEngine")


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

    def speak(self, message: str, config: Dict[str, Any]) -> None:
        """Invokes macOS native speech synthesizer (/usr/bin/say)."""
        persona = self.get_active_persona(config)
        voice = persona.get("voice", config.get("voice", "Moira"))
        rate = str(persona.get("speech_rate", config.get("speech_rate", 175)))

        logger.info("Speaking with voice '%s' (rate %s): %s", voice, rate, message)
        subprocess.run(["/usr/bin/say", "-v", voice, "-r", rate, message], check=False)
