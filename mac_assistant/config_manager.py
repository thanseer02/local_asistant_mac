"""Configuration loader and hot-reloading manager.

Modular file layout:
- `config.json`: Core assistant settings, user persona choice, volume/speech rates, and feature toggles (~70 lines).
- `schedule_times.json`: Clean, dedicated configuration for all intervals, working hours, and fixed daily alert times.
- `messages.json`: Dedicated message dictionary containing persona dialogues, greetings, goodbyes, and reminder speech pools.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("MacAssistant.Config")

CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent / "config.json"
SCHEDULE_FILE_PATH = Path(__file__).resolve().parent.parent / "schedule_times.json"
MESSAGES_FILE_PATH = Path(__file__).resolve().parent.parent / "messages.json"

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
    "speech_rate": 172,
    "user_name": "Sir",
    "login_delay_seconds": 0.5,
    "cooldown_seconds": 2,
    "listen_mode": "off",
    "hud_sound": {
        "enabled": True,
        "sound_file": "hud_chime.wav"
    },
    "audio_ducking": {
        "enabled": True,
        "duck_level": 0.25,
        "duck_system_volume": True
    },
    "morning_briefing": {
        "enabled": True,
        "include_weather": True,
        "include_calendar": False,
        "weather_location": ""
    },
    "git_briefing": {
        "enabled": True,
        "repositories": []
    },
    "focus_guard": {
        "enabled": True,
        "apps": ["Microsoft Teams", "Teams", "zoom.us", "Webex", "FaceTime"]
    },
    "skills": {
        "shortcuts": True,
        "media_control": True,
        "system_health": True,
        "memory": True
    },
    "startup_apps": {
        "enabled": True
    },
    "eye_break_reminders": {"enabled": True},
    "hydration_reminders": {"enabled": True},
    "late_night_reminders": {"enabled": True},
    "scheduled_reminders": []
}


class ConfigManager:
    """Manages loading and dynamic reloading across config.json, schedule_times.json, and messages.json."""

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

    @staticmethod
    def load_messages() -> Dict[str, Any]:
        """Loads messages.json, providing persona dialogues and alert speech pools."""
        if MESSAGES_FILE_PATH.exists():
            try:
                with open(MESSAGES_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to parse messages.json (%s).", e)
        return {}

    @classmethod
    def load(cls) -> Dict[str, Any]:
        """Loads configuration from disk, cleanly merging schedule_times.json and messages.json."""
        config_data = dict(DEFAULT_CONFIG)

        # 1. Load config.json
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    config_data.update(file_data)
            except Exception as e:
                logger.warning("Failed to parse config.json (%s). Using defaults.", e)

        # 2. Merge separate schedule_times.json
        times = cls.load_schedule_times()

        if "eye_break" in times:
            eye_cfg = config_data.setdefault("eye_break_reminders", {})
            if "interval_minutes" in times["eye_break"]:
                eye_cfg["interval_minutes"] = times["eye_break"]["interval_minutes"]

        if "hydration" in times:
            hydro_cfg = config_data.setdefault("hydration_reminders", {})
            for k in ("interval_minutes", "start_hour", "end_hour"):
                if k in times["hydration"]:
                    hydro_cfg[k] = times["hydration"][k]

        if "late_night" in times:
            late_cfg = config_data.setdefault("late_night_reminders", {})
            for k in ("interval_minutes", "start_hour", "end_hour"):
                if k in times["late_night"]:
                    late_cfg[k] = times["late_night"][k]

        # 3. Merge separate messages.json
        msgs = cls.load_messages()

        # Eye break messages
        if "eye_break_reminders" in msgs:
            eye_cfg = config_data.setdefault("eye_break_reminders", {})
            eye_cfg.update(msgs["eye_break_reminders"])

        # Hydration messages
        if "hydration_reminders" in msgs:
            hydro_cfg = config_data.setdefault("hydration_reminders", {})
            hydro_cfg.update(msgs["hydration_reminders"])

        # Late night messages
        if "late_night_reminders" in msgs:
            late_cfg = config_data.setdefault("late_night_reminders", {})
            late_cfg.update(msgs["late_night_reminders"])

        # Personas dialogue pools (greetings, goodbyes)
        if "persona_dialogues" in msgs:
            personas = config_data.setdefault("personas", {})
            for persona_name, dialogue_data in msgs["persona_dialogues"].items():
                p_cfg = personas.setdefault(persona_name, {})
                # preserve voice and rate settings if already set
                if "voice" not in p_cfg:
                    p_cfg["voice"] = "Moira" if persona_name == "friday" else "Daniel"
                if "speech_rate" not in p_cfg:
                    p_cfg["speech_rate"] = 172 if persona_name == "friday" else 162
                p_cfg.update(dialogue_data)

        # 4. Construct Scheduled Reminders by joining schedule_times and messages
        daily_dict = msgs.get("daily_reminders", {})
        fixed_alerts = times.get("fixed_daily_alerts", [])
        new_scheduled = []

        for item in fixed_alerts:
            t = item.get("time")
            if not t:
                continue
            entry = {"time": t}
            if t in daily_dict:
                entry.update(daily_dict[t])
            else:
                entry["friday_messages"] = [f"Sir, the clock strikes {t}. Time for your scheduled break."]
                entry["jarvis_messages"] = [f"Sir, pardon the intrusion. The time is {t}. May I suggest taking your scheduled break?"]
            new_scheduled.append(entry)

        config_data["scheduled_reminders"] = new_scheduled

        return config_data
