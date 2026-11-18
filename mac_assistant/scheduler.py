"""Scheduler for tea, lunch, go-home, late-night rest, 20-20-20 eye strain, and hydration alerts."""

import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, Optional

from .voice_engine import SpeechPriority, VoiceEngine

logger = logging.getLogger("MacAssistant.Scheduler")


class ReminderScheduler:
    """Evaluates time rules and triggers audio alerts for wellness, health, and schedule."""

    def __init__(self, voice_engine: VoiceEngine):
        self.engine = voice_engine
        self.last_checked_minute: Optional[str] = None
        self.last_late_night_time: float = 0
        self.last_eye_break_time: float = 0
        self.last_hydration_time: float = 0

    def check_scheduled(self, config: Dict[str, Any], current_time_str: str) -> bool:
        """Checks daily fixed reminders (tea, lunch, go home). Returns True if spoken."""
        if current_time_str == self.last_checked_minute:
            return False

        self.last_checked_minute = current_time_str
        persona_key = config.get("assistant_persona", "friday").lower()
        name = config.get("user_name", "Sir")

        for reminder in config.get("scheduled_reminders", []):
            if reminder.get("time") == current_time_str:
                template = reminder.get(f"{persona_key}_message") or reminder.get("message")
                if template:
                    msg = template.format(name=name, title=name)
                    logger.info("Triggering scheduled reminder (%s): %s", current_time_str, msg)
                    self.engine.speak(msg, config, priority=SpeechPriority.REMINDER)
                    return True
        return False

    def check_eye_break(self, config: Dict[str, Any], now_ts: float) -> bool:
        """Triggers the 20-20-20 rule reminder every 20 minutes (look 20 feet away for 20 seconds)."""
        eye_cfg = config.get("eye_break_reminders", {})
        if not eye_cfg.get("enabled", True):
            return False

        interval_secs = eye_cfg.get("interval_minutes", 20) * 60

        if self.last_eye_break_time == 0:
            self.last_eye_break_time = now_ts
            return False

        if now_ts - self.last_eye_break_time >= interval_secs:
            self.last_eye_break_time = now_ts
            persona_key = config.get("assistant_persona", "friday").lower()
            name = config.get("user_name", "Sir")
            messages = eye_cfg.get(f"{persona_key}_messages", [])
            if messages:
                msg = random.choice(messages).format(name=name, title=name)
                logger.info("Triggering 20-20-20 eye break reminder: %s", msg)
                self.engine.speak(msg, config, priority=SpeechPriority.REMINDER)
                return True
        return False

    def check_hydration(self, config: Dict[str, Any], now_ts: float) -> bool:
        """Triggers periodic hydration check-ins (e.g. every 45-60 minutes)."""
        hydro_cfg = config.get("hydration_reminders", {})
        if not hydro_cfg.get("enabled", True):
            return False

        interval_secs = hydro_cfg.get("interval_minutes", 45) * 60

        if self.last_hydration_time == 0:
            self.last_hydration_time = now_ts
            return False

        if now_ts - self.last_hydration_time >= interval_secs:
            self.last_hydration_time = now_ts
            persona_key = config.get("assistant_persona", "friday").lower()
            name = config.get("user_name", "Sir")
            messages = hydro_cfg.get(f"{persona_key}_messages", [])
            if messages:
                msg = random.choice(messages).format(name=name, title=name)
                logger.info("Triggering hydration reminder: %s", msg)
                self.engine.speak(msg, config, priority=SpeechPriority.REMINDER)
                return True
        return False

    def check_late_night(self, config: Dict[str, Any], now_dt: datetime, now_ts: float) -> bool:
        """Reminds the user every interval (e.g. 30 mins) during late night hours."""
        late_cfg = config.get("late_night_reminders", {})
        if not late_cfg.get("enabled", False):
            return False

        start_h = late_cfg.get("start_hour", 22)
        end_h = late_cfg.get("end_hour", 5)
        interval_secs = late_cfg.get("interval_minutes", 30) * 60
        current_hour = now_dt.hour

        is_late_night = (
            (current_hour >= start_h or current_hour < end_h)
            if start_h > end_h
            else (start_h <= current_hour < end_h)
        )

        if is_late_night and (now_ts - self.last_late_night_time >= interval_secs):
            if self.last_late_night_time == 0:
                self.last_late_night_time = now_ts
                return False
            else:
                self.last_late_night_time = now_ts
                persona_key = config.get("assistant_persona", "friday").lower()
                name = config.get("user_name", "Sir")
                messages = late_cfg.get(f"{persona_key}_messages", [])
                if messages:
                    msg = random.choice(messages).format(name=name, title=name)
                    logger.info("Triggering late night rest reminder: %s", msg)
                    self.engine.speak(msg, config, priority=SpeechPriority.REMINDER)
                    return True
        return False
