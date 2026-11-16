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
    "speech_rate": 175,
    "user_name": "Sir",
    "login_delay_seconds": 2,
    "cooldown_seconds": 3,
    "late_night_reminders": {
        "enabled": True,
        "start_hour": 22,
        "end_hour": 5,
        "interval_minutes": 30,
        "friday_messages": [
            "Sir, it's getting quite late. You've been working hard; please take a rest.",
            "Sir, 30 minutes have passed. Remember to take a break and step away from the screen."
        ],
        "jarvis_messages": [
            "Pardon the interruption. The hour is late, Sir. Might I strongly recommend taking a rest?",
            "Another 30 minutes have elapsed, Sir. A brief respite would be prudent."
        ]
    },
    "scheduled_reminders": [],
    "personas": {
        "friday": {
            "voice": "Moira",
            "speech_rate": 175,
            "greetings": {
                "morning": ["Sir, good morning! Friday online."],
                "afternoon": ["Sir, good afternoon. Friday standing by."],
                "evening": ["Sir, good evening. Friday online."],
                "night": ["Sir, working late tonight? Don't push yourself too hard."]
            }
        },
        "jarvis": {
            "voice": "Daniel",
            "speech_rate": 170,
            "greetings": {
                "morning": ["Good morning. Jarvis online, Sir."],
                "afternoon": ["Good afternoon. Jarvis at your service, Sir."],
                "evening": ["Good evening. Jarvis online, Sir."],
                "night": ["Working late? Might I recommend getting some rest shortly, Sir?"]
            }
        }
    }
}


class ConfigManager:
    """Manages loading and dynamic reloading of config.json."""

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
