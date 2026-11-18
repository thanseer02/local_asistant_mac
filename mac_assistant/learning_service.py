"""Learns user habits, routines, and command corrections over time."""

from collections import Counter
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.RoutineLearning")

HABITS_FILE = Path(__file__).resolve().parent.parent / "data" / "habits.json"


class RoutineLearningService:
    """Tracks command usage patterns, routine wake hours, and user corrections."""

    def __init__(self, habits_path: Optional[Path] = None):
        self.path = habits_path or HABITS_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "wake_hours": [],
            "frequent_apps": {},
            "corrections": {}
        }

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.debug("Failed saving habits: %s", e)

    def record_wake(self) -> None:
        hour = datetime.now().hour
        self.data.setdefault("wake_hours", []).append(hour)
        if len(self.data["wake_hours"]) > 100:
            self.data["wake_hours"] = self.data["wake_hours"][-100:]
        self._save()

    def record_app_launch(self, app_name: str) -> None:
        counts = self.data.setdefault("frequent_apps", {})
        counts[app_name] = counts.get(app_name, 0) + 1
        self._save()

    def record_correction(self, original_misunderstood: str, user_intended: str) -> None:
        """Saves user correction ('no, I meant Chrome') to override future misinterpretations."""
        corrections = self.data.setdefault("corrections", {})
        corrections[original_misunderstood.lower().strip()] = user_intended.lower().strip()
        self._save()
        logger.info("Learned user correction: '%s' -> '%s'", original_misunderstood, user_intended)

    def get_corrected_intent(self, text: str) -> str:
        clean = text.lower().strip()
        return self.data.get("corrections", {}).get(clean, text)
