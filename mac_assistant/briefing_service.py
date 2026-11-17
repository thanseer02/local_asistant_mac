"""Briefing service providing weather, calendar agenda, and daily overview."""

import json
import logging
import subprocess
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.Briefing")


class BriefingService:
    """Fetches local weather and calendar/reminders for morning briefing."""

    @staticmethod
    def get_weather(location: str = "") -> Optional[str]:
        """
        Fetches current weather via wttr.in.
        Returns a clean short summary string like '28°C and clear sky'.
        """
        query = f"https://wttr.in/{location}?format=%t+and+%C"
        try:
            req = urllib.request.Request(
                query,
                headers={"User-Agent": "curl/7.88.1"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                text = resp.read().decode("utf-8").strip()
                # Clean up format (e.g. "+28°C and Sunny" -> "28°C and Sunny")
                text = text.replace("+", "")
                if text and not text.startswith("<") and "unknown" not in text.lower():
                    return text
        except Exception as e:
            logger.debug("Weather fetch skipped or unavailable: %s", e)
        return None

    @staticmethod
    def get_upcoming_tasks() -> List[str]:
        """Queries Apple Reminders for uncompleted tasks due today."""
        script = '''
        tell application "Reminders"
            set taskList to {}
            try
                repeat with l in lists
                    repeat with r in (reminders of l whose completed is false)
                        set end of taskList to (name of r)
                        if (count of taskList) >= 3 then exit repeat
                    end repeat
                    if (count of taskList) >= 3 then exit repeat
                end repeat
            end try
            return taskList
        end tell
        '''
        try:
            res = subprocess.run(
                ["/usr/bin/osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=4
            )
            raw = res.stdout.strip()
            if raw:
                tasks = [t.strip() for t in raw.split(", ") if t.strip()]
                return tasks[:3]
        except Exception as e:
            logger.debug("Could not query Reminders: %s", e)
        return []

    @classmethod
    def generate_morning_briefing(cls, config: Dict[str, Any]) -> str:
        """Constructs an intelligent morning briefing combining greeting, weather, and tasks."""
        briefing_cfg = config.get("morning_briefing", {})
        if not briefing_cfg.get("enabled", True):
            return ""

        persona_key = config.get("assistant_persona", "friday").lower()
        location = briefing_cfg.get("weather_location", "")
        weather = cls.get_weather(location) if briefing_cfg.get("include_weather", True) else None
        tasks = cls.get_upcoming_tasks() if briefing_cfg.get("include_calendar", True) else []

        lines = []

        # Weather statement
        if weather:
            if persona_key == "jarvis":
                lines.append(f"Current local conditions are reporting {weather}.")
            else:
                lines.append(f"Current weather is {weather}.")

        # Tasks / Agenda statement
        if tasks:
            task_str = ", ".join(tasks[:2])
            if persona_key == "jarvis":
                lines.append(f"You have pending tasks on your agenda, including {task_str}.")
            else:
                lines.append(f"You've got {len(tasks)} items on your reminder list, including {task_str}.")

        if not lines:
            return ""

        return " ".join(lines)
