"""Configuration loader and hot-reloading manager with Pydantic validation."""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from .config_schema import AppConfigSchema

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
    """Manages loading, updating, validation, and dynamic reloading of config.json."""

    @staticmethod
    def load() -> Dict[str, Any]:
        """Loads configuration from disk, validating against Pydantic schema and falling back safely."""
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # Validate with Pydantic schema
                validated = AppConfigSchema(**raw_data)
                return {**DEFAULT_CONFIG, **raw_data}
            except Exception as e:
                logger.warning("Configuration validation/parse issue in config.json: %s. Using safe defaults.", e)
        return DEFAULT_CONFIG

    @classmethod
    def set_active_persona(cls, persona_name: str) -> None:
        """Dynamically switches the active persona ('friday' or 'jarvis') and persists to config.json."""
        target = persona_name.lower().strip()
        if target not in ["friday", "jarvis"]:
            return

        config = cls.load()
        if config.get("assistant_persona") == target:
            return

        config["assistant_persona"] = target
        if "personas" in config and target in config["personas"]:
            profile = config["personas"][target]
            config["voice"] = profile.get("voice", config.get("voice"))
            config["speech_rate"] = profile.get("speech_rate", config.get("speech_rate"))

        cls.save(config)
        logger.info("Persona dynamically switched to '%s' and saved.", target)

    @staticmethod
    def save(config_data: Dict[str, Any]) -> bool:
        """Writes configuration to config.json safely."""
        try:
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
            return True
        except Exception as e:
            logger.error("Failed saving configuration to %s: %s", CONFIG_FILE_PATH, e)
            return False
