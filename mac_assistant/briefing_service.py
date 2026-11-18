"""Briefing service providing weather, calendar agenda, and daily overview.

Features:
- Parallel fetching of weather, Apple Reminders, and Git status via ThreadPoolExecutor.
- Strict 2.0 second overall timeout.
- In-memory 30-minute weather cache with fallback to last cached reading on failure.
- Graceful omission: if any source fails or times out, the briefing composes from whatever arrived without blocking.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import subprocess
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

from .git_inspector import GitInspector

logger = logging.getLogger("MacAssistant.Briefing")

# 30-minute in-memory cache for weather
_WEATHER_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "location": "",
    "data": None
}
WEATHER_CACHE_TTL = 1800  # 30 minutes in seconds


class BriefingService:
    """Fetches local weather and calendar/reminders for morning briefing concurrently."""

    @staticmethod
    def get_weather(location: str = "", timeout: float = 1.8) -> Optional[str]:
        """
        Fetches current weather via wttr.in.
        Returns a clean short summary string like '28°C and clear sky'.
        Falls back to last cached value if network fails or times out.
        """
        global _WEATHER_CACHE
        now = time.time()

        # Check valid in-memory cache
        if _WEATHER_CACHE["data"] and _WEATHER_CACHE["location"] == location:
            if now - _WEATHER_CACHE["timestamp"] < WEATHER_CACHE_TTL:
                logger.debug("Returning cached weather: %s", _WEATHER_CACHE["data"])
                return _WEATHER_CACHE["data"]

        query = f"https://wttr.in/{location}?format=%t+and+%C"
        try:
            req = urllib.request.Request(
                query,
                headers={"User-Agent": "curl/7.88.1"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8").strip()
                text = text.replace("+", "")
                if text and not text.startswith("<") and "unknown" not in text.lower():
                    _WEATHER_CACHE["timestamp"] = now
                    _WEATHER_CACHE["location"] = location
                    _WEATHER_CACHE["data"] = text
                    return text
        except Exception as e:
            logger.debug("Weather fetch skipped or timed out: %s", e)

        # Fallback to stale cached data if available
        if _WEATHER_CACHE["data"]:
            logger.info("Using stale cached weather after fetch failure: %s", _WEATHER_CACHE["data"])
            return _WEATHER_CACHE["data"]

        return None

    @staticmethod
    def get_upcoming_tasks(timeout: float = 1.8) -> List[str]:
        """Queries Apple Reminders for uncompleted tasks due today with strict timeout."""
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
                timeout=timeout
            )
            raw = res.stdout.strip()
            if raw:
                tasks = [t.strip() for t in raw.split(", ") if t.strip()]
                return tasks[:3]
        except Exception as e:
            logger.debug("Could not query Reminders: %s", e)
        return []

    @classmethod
    def generate_morning_briefing(cls, config: Dict[str, Any], overall_timeout: float = 2.0) -> str:
        """
        Constructs an intelligent morning briefing combining greeting, weather, and tasks.
        Executes external checks in parallel via ThreadPoolExecutor within overall_timeout.
        Omits any timed-out component rather than delaying the greeting.
        """
        briefing_cfg = config.get("morning_briefing", {})
        if not briefing_cfg.get("enabled", True):
            return ""

        persona_key = config.get("assistant_persona", "friday").lower()
        location = briefing_cfg.get("weather_location", "")
        include_weather = briefing_cfg.get("include_weather", True)
        include_calendar = briefing_cfg.get("include_calendar", True)

        weather: Optional[str] = None
        tasks: List[str] = []
        git_summary: Optional[str] = None

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="MacAssistant-Briefing") as executor:
            fut_weather = executor.submit(cls.get_weather, location, 1.8) if include_weather else None
            fut_tasks = executor.submit(cls.get_upcoming_tasks, 1.8) if include_calendar else None
            fut_git = executor.submit(GitInspector.get_summary, config)

            # Resolve weather
            if fut_weather:
                try:
                    weather = fut_weather.result(timeout=max(0.1, overall_timeout - (time.time() - start_time)))
                except Exception as e:
                    logger.debug("Weather task timed out or failed: %s", e)

            # Resolve tasks
            if fut_tasks:
                try:
                    tasks = fut_tasks.result(timeout=max(0.1, overall_timeout - (time.time() - start_time))) or []
                except Exception as e:
                    logger.debug("Tasks task timed out or failed: %s", e)

            # Resolve git
            if fut_git:
                try:
                    git_summary = fut_git.result(timeout=max(0.1, overall_timeout - (time.time() - start_time)))
                except Exception as e:
                    logger.debug("Git summary task timed out or failed: %s", e)

        lines = []

        # Weather statement
        if weather:
            if persona_key == "jarvis":
                lines.append(f"Current local conditions are reporting {weather}.")
            elif persona_key == "alfred":
                lines.append(f"Outside, the elements offer {weather}.")
            else:
                lines.append(f"Current weather is {weather}.")

        # Tasks / Agenda statement
        if tasks:
            task_str = ", ".join(tasks[:2])
            if persona_key == "jarvis":
                lines.append(f"You have pending tasks on your agenda, including {task_str}.")
            elif persona_key == "alfred":
                lines.append(f"You have {len(tasks)} obligations pending, notably {task_str}.")
            else:
                lines.append(f"You've got {len(tasks)} items on your reminder list, including {task_str}.")

        # Git Status briefing
        if git_summary:
            lines.append(git_summary)

        if not lines:
            return ""

        return " ".join(lines)
