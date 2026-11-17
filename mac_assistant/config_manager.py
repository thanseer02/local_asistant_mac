"""Configuration loader and hot-reloading manager."""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("MacAssistant.Config")

CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "assistant_persona": "friday",
    "voice": "Moira",
    "speech_rate": 172,
    "user_name": "Sir",
    "login_delay_seconds": 0.5,
    "cooldown_seconds": 2,
    "hud_sound": {
        "enabled": True,
        "sound_file": "hud_chime.wav"
    },
    "voice_commands": {
        "enabled": False,
        "wake_words": ["hey jarvis", "hey friday", "jarvis", "friday"],
        "mic_index": None
    },
    "startup_apps": {
        "enabled": True
    },
    "personas": {
        "friday": {
            "voice": "Moira",
            "speech_rate": 172
        },
        "jarvis": {
            "voice": "Daniel",
            "speech_rate": 162
        }
    }
}


class ConfigManager:
    """Manages loading, updating, and dynamic reloading of config.json."""

    @staticmethod
    def load() -> Dict[str, Any]:
        """Loads configuration from disk, safely falling back to defaults."""
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {**DEFAULT_CONFIG, **data}
            except Exception as e:
                logger.warning("Failed to parse config.json (%s). Using defaults.", e)
        return DEFAULT_CONFIG

    @classmethod
    def set_active_persona(cls, persona_name: str) -> None:
        """
        Dynamically switches the active persona ('friday' or 'jarvis')
        and persists it to config.json as the new default!
        """
        target = persona_name.lower().strip()
        if target not in ["friday", "jarvis"]:
            return

        config = cls.load()
        if config.get("assistant_persona") == target:
            return

        config["assistant_persona"] = target
        if target == "jarvis":
            config["voice"] = "Daniel"
            config["speech_rate"] = 162
        else:
            config["voice"] = "Moira"
            config["speech_rate"] = 172

        try:
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info("Persisted '%s' as the new active default assistant persona in config.json.", target)
        except Exception as e:
            logger.error("Failed saving new default persona to config.json: %s", e)
