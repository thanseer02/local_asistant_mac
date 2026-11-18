"""Dedicated configuration for Jarvis personality and voice delivery."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "config.json"


class JarvisPersonalityConfig(BaseModel):
    """
    Configuration model for Jarvis's personality, speaking style, and voice delivery:
    - Tone: Sophisticated, intelligent, calm, confident, analytical, polished, and subtly witty.
    - Speaking Style: Concise natural speech, precise, articulate.
    - Salutation: Occasional respectful use of 'Sir'.
    - Safety: Strictly honors tools and permissions; never executes unauthorized commands.
    """
    personality: str = "sophisticated_butler"  # sophisticated_butler, analytical_executive
    speaking_style: str = "articulate_polished" # articulate_polished, formal, concise
    response_length: str = "concise"            # concise, detailed, adaptive
    humor: bool = True                          # Subtle British-style wit
    emotional_awareness: bool = True            # Composed recognition without claiming human feelings
    use_conversation_context: bool = True
    avoid_repetitive_greetings: bool = True
    language: str = "English"
    use_salutation: bool = True                 # Occasional respectful use of Sir
    salutation_title: str = "Sir"
    max_history_turns: int = 15
    persist_memory_sqlite: bool = True
    voice: str = "Daniel"                       # British English classic Jarvis voice
    speech_rate: int = 162


class JarvisPersonalityManager:
    """Manages active Jarvis personality parameters with live adjustment via voice commands."""

    _instance: Optional["JarvisPersonalityManager"] = None

    def __init__(self):
        self.config = JarvisPersonalityConfig()
        self._load_from_config_json()

    @classmethod
    def get_instance(cls) -> "JarvisPersonalityManager":
        if cls._instance is None:
            cls._instance = JarvisPersonalityManager()
        return cls._instance

    def _load_from_config_json(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                j_cfg = data.get("jarvis_personality_settings", {})
                if j_cfg:
                    self.config = JarvisPersonalityConfig(**j_cfg)
            except Exception:
                pass

    def save_to_config_json(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["jarvis_personality_settings"] = self.config.model_dump()
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def set_personality(self, name: str) -> str:
        self.config.personality = name
        self.save_to_config_json()
        return f"Jarvis personality updated to {name.replace('_', ' ')}."

    def set_response_length(self, length: str) -> str:
        if length in ["concise", "detailed", "adaptive"]:
            self.config.response_length = length
            self.save_to_config_json()
            return f"Jarvis response length set to {length}."
        return "Allowed response lengths are concise, detailed, or adaptive."

    def toggle_humor(self, enable: Optional[bool] = None) -> str:
        if enable is None:
            self.config.humor = not self.config.humor
        else:
            self.config.humor = enable
        self.save_to_config_json()
        status = "enabled" if self.config.humor else "disabled"
        return f"Jarvis wit and humor are now {status}."
