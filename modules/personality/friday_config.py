"""Dedicated configuration for Friday personality and voice delivery."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "config.json"


class FridayPersonalityConfig(BaseModel):
    """Configuration model for Friday's personality and voice delivery."""
    personality: str = "professional_friendly"  # professional_friendly, casual_humorous, concise_butler
    speaking_style: str = "natural"            # natural, formal, expressive
    response_length: str = "concise"           # concise, detailed, adaptive
    humor: bool = True
    emotional_awareness: bool = True
    use_conversation_context: bool = True
    avoid_repetitive_greetings: bool = True
    language: str = "English"
    use_salutation: bool = True                 # True to address the user as 'Boss'
    salutation_title: str = "Boss"
    max_history_turns: int = 15
    persist_memory_sqlite: bool = True
    voice: str = "Moira"
    speech_rate: int = 172


class FridayPersonalityManager:
    """Manages active Friday personality parameters with live adjustment via voice commands."""

    _instance: Optional["FridayPersonalityManager"] = None

    def __init__(self):
        self.config = FridayPersonalityConfig()
        self._load_from_config_json()

    @classmethod
    def get_instance(cls) -> "FridayPersonalityManager":
        if cls._instance is None:
            cls._instance = FridayPersonalityManager()
        return cls._instance

    def _load_from_config_json(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                p_cfg = data.get("friday_personality_settings") or data.get("personality_settings", {})
                if p_cfg:
                    self.config = FridayPersonalityConfig(**p_cfg)
            except Exception:
                pass

    def save_to_config_json(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dump = self.config.model_dump()
                data["friday_personality_settings"] = dump
                data["personality_settings"] = dump
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def set_personality(self, name: str) -> str:
        self.config.personality = name
        self.save_to_config_json()
        return f"Friday personality updated to {name.replace('_', ' ')}."

    def set_response_length(self, length: str) -> str:
        if length in ["concise", "detailed", "adaptive"]:
            self.config.response_length = length
            self.save_to_config_json()
            return f"Friday response length set to {length}."
        return "Allowed response lengths are concise, detailed, or adaptive."

    def toggle_humor(self, enable: Optional[bool] = None) -> str:
        if enable is None:
            self.config.humor = not self.config.humor
        else:
            self.config.humor = enable
        self.save_to_config_json()
        status = "enabled" if self.config.humor else "disabled"
        return f"Humor is now {status}."


# Backward compatibility alias
PersonalityManager = FridayPersonalityManager
