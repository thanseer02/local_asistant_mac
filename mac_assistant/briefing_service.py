"""Briefing service providing weather, calendar agenda, git updates, and daily overview.

Runs external fetches concurrently via ThreadPoolExecutor with caching,
timeouts, and graceful fallbacks so greetings never stall.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import logging
import subprocess
import time
import urllib.request
from typing import Any, Dict, List, Optional

from .git_inspector import GitInspector

logger = logging.getLogger("MacAssistant.Briefing")

_WEATHER_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "location": "",
    "data": None
}
WEATHER_CACHE_TTL = 1800  # 30 minutes in seconds


class BriefingService:
    """Fetches local weather and calendar/reminders for morning briefing concurrently."""

    @staticmethod
    def get_weather(location: str = "", timeout: float = 3.0) -> Optional[str]:
        """Fetches current weather via wttr.in with 30-minute caching and retry fallback."""
        global _WEATHER_CACHE
        now = time.time()

        if _WEATHER_CACHE["data"] and _WEATHER_CACHE["location"] == location:
            if now - _WEATHER_CACHE["timestamp"] < WEATHER_CACHE_TTL:
                return _WEATHER_CACHE["data"]

        query = f"https://wttr.in/{location}?format=%t+and+%C"
        for attempt in range(2):
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
                logger.debug("Weather fetch attempt %d failed: %s", attempt + 1, e)
                if attempt == 0:
                    time.sleep(0.5)

        return _WEATHER_CACHE.get("data")  # Return stale cache if available or None

    @staticmethod
    def get_upcoming_tasks(timeout: float = 2.5) -> List[str]:
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
                timeout=timeout
            )
            raw = res.stdout.strip()
            if raw:
                tasks = [t.strip() for t in raw.split(", ") if t.strip()]
                return tasks[:3]
        except Exception as e:
            logger.debug("Could not query Reminders within timeout: %s", e)
        return []

    @classmethod
    def get_briefing_data_concurrent(cls, config: Dict[str, Any], timeout: float = 4.0) -> Dict[str, Any]:
        """Fetches weather, tasks, and git status concurrently with strict total timeout."""
        location = config.get("morning_briefing", {}).get("weather_location", "")

        data: Dict[str, Any] = {
            "weather": None,
            "tasks": [],
            "git_summary": None
        }

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="BriefingWorker") as executor:
            fut_weather = executor.submit(cls.get_weather, location, 3.0)
            fut_tasks = executor.submit(cls.get_upcoming_tasks, 2.5)
            fut_git = executor.submit(GitInspector.get_summary, config)

            try:
                data["weather"] = fut_weather.result(timeout=timeout)
            except Exception as e:
                logger.debug("Weather task timed out: %s", e)

            try:
                data["tasks"] = fut_tasks.result(timeout=timeout)
            except Exception as e:
                logger.debug("Reminders task timed out: %s", e)

            try:
                data["git_summary"] = fut_git.result(timeout=timeout)
            except Exception as e:
                logger.debug("Git inspection timed out: %s", e)

        return data

    @classmethod
    def generate_morning_briefing(cls, config: Dict[str, Any]) -> str:
        """Constructs an intelligent, prioritized morning briefing under 30 seconds spoken length."""
        briefing_cfg = config.get("morning_briefing", {})
        if not briefing_cfg.get("enabled", True):
            return ""

        persona_key = config.get("assistant_persona", "friday").lower()
        now = datetime.now()

        # Check morning window (e.g. 6 AM to 11:30 AM)
        start_hour = briefing_cfg.get("start_hour", 6)
        end_hour = briefing_cfg.get("end_hour", 12)
        if not (start_hour <= now.hour < end_hour):
            return ""

        data = cls.get_briefing_data_concurrent(config, timeout=3.5)
        weather_text = data.get("weather")
        tasks = data.get("tasks", [])
        git_summary = data.get("git_summary")

        parts: List[str] = []

        # Weather segment
        if weather_text:
            if persona_key == "jarvis":
                parts.append(f"Current conditions outside indicate {weather_text}.")
            else:
                parts.append(f"Weather right now is {weather_text}.")

        # Reminders / agenda segment
        if tasks:
            task_str = ", ".join(tasks[:2])
            if persona_key == "jarvis":
                parts.append(f"You have {len(tasks)} pressing items on your agenda, including {task_str}.")
            else:
                parts.append(f"You've got {len(tasks)} reminders today: {task_str}.")

        # Git status segment
        if git_summary:
            parts.append(git_summary)

        return " ".join(parts).strip()
