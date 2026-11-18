"""Configuration loader and hot-reloading manager.

Loads:
- `config.json`: Persona, voice rate, greetings, and system settings.
- `schedule_times.json`: Clean dedicated file for all reminder timings, intervals, and schedules.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("MacAssistant.Config")

CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent / "config.json"
SCHEDULE_FILE_PATH = Path(__file__).resolve().parent.parent / "schedule_times.json"

DEFAULT_SCHEDULE_TIMES: Dict[str, Any] = {
    "eye_break": {
        "interval_minutes": 20
    },
    "hydration": {
        "interval_minutes": 45,
        "start_hour": 9,
        "end_hour": 18
    },
    "late_night": {
        "start_hour": 22,
        "end_hour": 5,
        "interval_minutes": 30
    },
    "fixed_daily_alerts": [
        {"time": "11:00", "label": "Morning Tea"},
        {"time": "13:00", "label": "Lunch"},
        {"time": "16:00", "label": "Afternoon Tea"},
        {"time": "18:18", "label": "End of Workday"}
    ]
}

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
    """Manages loading and dynamic reloading of config.json and schedule_times.json."""

    @staticmethod
    def load_schedule_times() -> Dict[str, Any]:
        """Loads schedule_times.json, falling back to defaults if missing or corrupt."""
        if SCHEDULE_FILE_PATH.exists():
            try:
                with open(SCHEDULE_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {**DEFAULT_SCHEDULE_TIMES, **data}
            except Exception as e:
                logger.warning("Failed to parse schedule_times.json (%s). Using default schedule.", e)
        return DEFAULT_SCHEDULE_TIMES

    @classmethod
    def load(cls) -> Dict[str, Any]:
        """Loads configuration from disk, overlaying schedule_times.json onto timing settings."""
        config_data = dict(DEFAULT_CONFIG)
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    config_data.update(file_data)
            except Exception as e:
                logger.warning("Failed to parse config.json (%s). Using defaults.", e)

        # Merge separate schedule_times.json
        times = cls.load_schedule_times()

        # 1. Overlay Eye break interval
        if "eye_break" in times:
            eye_cfg = config_data.setdefault("eye_break_reminders", {})
            if "interval_minutes" in times["eye_break"]:
                eye_cfg["interval_minutes"] = times["eye_break"]["interval_minutes"]

        # 2. Overlay Hydration timings
        if "hydration" in times:
            hydro_cfg = config_data.setdefault("hydration_reminders", {})
            for k in ("interval_minutes", "start_hour", "end_hour"):
                if k in times["hydration"]:
                    hydro_cfg[k] = times["hydration"][k]

        # 3. Overlay Late Night window
        if "late_night" in times:
            late_cfg = config_data.setdefault("late_night_reminders", {})
            for k in ("interval_minutes", "start_hour", "end_hour"):
                if k in times["late_night"]:
                    late_cfg[k] = times["late_night"][k]

        # 4. Overlay Fixed Daily scheduled reminders
        if "fixed_daily_alerts" in times and isinstance(times["fixed_daily_alerts"], list):
            existing_scheduled = config_data.get("scheduled_reminders", [])
            # Map existing reminders by their index or time for message templates
            new_scheduled = []
            for item in times["fixed_daily_alerts"]:
                t = item.get("time")
                if not t:
                    continue
                # Find matching message template from existing list or default
                matched = next((r for r in existing_scheduled if r.get("time") == t), None)
                if matched:
                    entry = dict(matched)
                elif existing_scheduled:
                    # fallback to first available template structure
                    entry = dict(existing_scheduled[0])
                    entry["time"] = t
                else:
                    entry = {
                        "time": t,
                        "friday_message": f"Sir, the clock strikes {t}. Time for your scheduled break.",
                        "jarvis_message": f"Sir, pardon the intrusion. The time is {t}. May I suggest taking your scheduled break?"
                    }
                entry["time"] = t
                new_scheduled.append(entry)

            if new_scheduled:
                config_data["scheduled_reminders"] = new_scheduled

        return config_data
