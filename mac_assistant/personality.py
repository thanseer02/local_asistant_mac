"""Persona Engine, Context Resolver, Mood & Escalation System.

Provides:
- Hot-reloadable persona JSON loading from `personas/*.json` with safe defaults.
- Zero-repeat line picker with rolling history window and weighted randomness.
- Contextual line selection: time of day, day of week, weather, workloads (git/tasks), streaks, quick unlocks.
- Mood engine: calm, playful, concerned, stern with natural decay over time.
- Late-night escalation levels (1, 2, 3) and reminder escalation that never turns rude.
- Voice modulation: embedded pauses ([[slnc 200]]) and speech rate/pitch shifts.
- Rare (3%) daily non-repeating easter eggs.
"""

from collections import deque
from dataclasses import dataclass, field
import datetime
import json
import logging
import os
from pathlib import Path
import random
import re
import time
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("MacAssistant.Personality")

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"
FALLBACK_PERSONA_ID = "friday"


@dataclass
class PersonaMoodState:
    current_mood: str = "calm"  # calm, playful, concerned, stern
    last_update_ts: float = field(default_factory=time.time)
    consecutive_ignored_reminders: int = 0
    consecutive_late_night_nudges: int = 0
    first_unlock_today: Optional[float] = None
    last_unlock_ts: float = 0.0
    daily_easter_eggs_fired: Set[str] = field(default_factory=set)
    daily_fired_date: str = ""

    def decay(self) -> None:
        """Decays heightened moods (playful, concerned, stern) back to calm over 45 minutes."""
        now = time.time()
        elapsed = now - self.last_update_ts
        today_str = datetime.date.today().isoformat()

        if self.daily_fired_date != today_str:
            self.daily_fired_date = today_str
            self.daily_easter_eggs_fired.clear()
            self.consecutive_late_night_nudges = 0
            self.first_unlock_today = None

        if elapsed > 2700:  # 45 minutes
            if self.current_mood != "calm":
                logger.debug("Mood decayed from %s back to calm after %.1f min.", self.current_mood, elapsed / 60)
                self.current_mood = "calm"
                self.consecutive_ignored_reminders = 0
            self.last_update_ts = now


class PersonaEngine:
    """Core personality system handling dialogues, mood transitions, and context rendering."""

    def __init__(self):
        self._personas: Dict[str, Dict[str, Any]] = {}
        self._recent_picks: Dict[str, Deque[str]] = {}  # key: f"{persona}_{event}" -> deque of last 6 picks
        self._history_window = 6
        self._mood_state = PersonaMoodState()
        self.reload_personas()

    def reload_personas(self) -> None:
        """Scans personas/ directory and hot-reloads all available persona definitions."""
        if not PERSONAS_DIR.exists():
            PERSONAS_DIR.mkdir(parents=True, exist_ok=True)

        found: Dict[str, Dict[str, Any]] = {}
        for path in PERSONAS_DIR.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pid = data.get("id", path.stem).lower()
                    found[pid] = data
            except Exception as e:
                logger.warning("Failed to load persona file %s (%s).", path.name, e)

        self._personas = found
        logger.debug("Loaded %d personas: %s", len(self._personas), list(self._personas.keys()))

    def get_persona(self, persona_id: str) -> Dict[str, Any]:
        """Returns the persona definition, safely falling back to friday or first available."""
        self.reload_personas()
        pid = (persona_id or "").lower().strip()
        if pid in self._personas:
            return self._personas[pid]
        if FALLBACK_PERSONA_ID in self._personas:
            return self._personas[FALLBACK_PERSONA_ID]
        if self._personas:
            return next(iter(self._personas.values()))

        # Hard emergency fallback if directory was completely empty
        return {
            "id": "friday",
            "name": "F.R.I.D.A.Y.",
            "voice": "Moira",
            "base_rate": 172,
            "address_terms": ["Sir"],
            "line_pools": {}
        }

    def resolve_auto_persona(self, config: Dict[str, Any]) -> str:
        """Resolves active persona based on time windows if auto_persona is configured."""
        auto_cfg = config.get("auto_persona")
        if isinstance(auto_cfg, dict):
            hour = datetime.datetime.now().hour
            # E.g. {"work_hours": [9, 18], "work_persona": "jarvis", "off_persona": "friday"}
            work_start, work_end = auto_cfg.get("work_hours", [9, 18])
            if work_start <= hour < work_end:
                return auto_cfg.get("work_persona", "jarvis")
            return auto_cfg.get("off_persona", "friday")

        return config.get("assistant_persona") or config.get("persona") or "friday"

    def record_unlock(self) -> Tuple[bool, float]:
        """Tracks unlock events. Returns (is_quick_unlock, continuous_session_hours)."""
        now = time.time()
        self._mood_state.decay()

        if self._mood_state.first_unlock_today is None:
            self._mood_state.first_unlock_today = now

        last = self._mood_state.last_unlock_ts
        self._mood_state.last_unlock_ts = now

        quick_unlock = (last > 0 and (now - last) < 120.0)  # under 2 minutes
        session_hours = max(0.0, (now - self._mood_state.first_unlock_today) / 3600.0)

        # Reset ignored reminders on active user unlock
        self._mood_state.consecutive_ignored_reminders = 0

        return quick_unlock, session_hours

    def record_reminder_fired(self) -> int:
        """Tracks consecutive reminder firings to calculate escalation levels."""
        self._mood_state.decay()
        self._mood_state.consecutive_ignored_reminders += 1
        # Escalate mood to concerned or stern if repeatedly ignored
        if self._mood_state.consecutive_ignored_reminders >= 3:
            self._mood_state.current_mood = "concerned"
        if self._mood_state.consecutive_ignored_reminders >= 5:
            self._mood_state.current_mood = "stern"
        self._mood_state.last_update_ts = time.time()
        return self._mood_state.consecutive_ignored_reminders

    def record_late_night_nudge(self) -> int:
        """Tracks late-night reminder escalations (1, 2, 3)."""
        self._mood_state.decay()
        self._mood_state.consecutive_late_night_nudges += 1
        if self._mood_state.consecutive_late_night_nudges >= 3:
            self._mood_state.current_mood = "stern"
        elif self._mood_state.consecutive_late_night_nudges >= 2:
            self._mood_state.current_mood = "concerned"
        self._mood_state.last_update_ts = time.time()
        return min(3, self._mood_state.consecutive_late_night_nudges)

    def pick(
        self,
        event: str,
        context: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, int]:
        """Picks a witty, non-repeating, context-aware line and computes the adjusted speech rate.

        Returns (speech_text, speech_rate).
        """
        if context is None:
            context = {}
        if config is None:
            config = {}

        persona_id = self.resolve_auto_persona(config)
        persona = self.get_persona(persona_id)
        personality_cfg = config.get("personality", {})

        humor_level = personality_cfg.get("humor_level", 2)       # 0=purely functional, 3=maximum banter
        easter_eggs_enabled = personality_cfg.get("easter_eggs", True)
        self._mood_state.decay()

        # Rare 3% chance for easter egg line on greetings or briefings (once per day)
        if easter_eggs_enabled and humor_level > 0 and event in ("unlock_greeting", "morning_briefing_intro"):
            eggs = persona.get("line_pools", {}).get("easter_eggs", [])
            unseen_eggs = [e for e in eggs if e not in self._mood_state.daily_easter_eggs_fired]
            if unseen_eggs and random.random() < 0.03:
                chosen_egg = random.choice(unseen_eggs)
                self._mood_state.daily_easter_eggs_fired.add(chosen_egg)
                logger.info("Triggered rare easter egg: %s", chosen_egg)
                return self._render_template(chosen_egg, context, persona), persona.get("base_rate", 170)

        # Retrieve candidate lines from persona line pools
        raw_pool = persona.get("line_pools", {}).get(event, [])
        candidates = self._select_candidates(event, raw_pool, context)

        if not candidates:
            # Fallback text if event pool is missing
            fallback_text = f"Welcome back, {context.get('name', 'Sir')}."
            return fallback_text, persona.get("base_rate", 170)

        # Non-repeating selection via history window
        history_key = f"{persona['id']}_{event}"
        if history_key not in self._recent_picks:
            self._recent_picks[history_key] = deque(maxlen=self._history_window)

        recent = self._recent_picks[history_key]
        filtered = [c for c in candidates if c not in recent]
        chosen = random.choice(filtered) if filtered else random.choice(candidates)
        recent.append(chosen)

        # Apply rate/pitch adjustments from mood
        mood = self._mood_state.current_mood
        mood_cfg = persona.get("mood_tuning", {}).get(mood, {"rate_offset": 0, "pitch_mod": ""})
        rate_offset = mood_cfg.get("rate_offset", 0)
        pitch_mod = mood_cfg.get("pitch_mod", "")

        adjusted_rate = max(130, min(220, persona.get("base_rate", 170) + rate_offset))
        rendered_text = self._render_template(chosen, context, persona)

        # Prefix pitch command if defined
        if pitch_mod and not rendered_text.startswith("[["):
            rendered_text = f"{pitch_mod} {rendered_text}"

        return rendered_text, adjusted_rate

    def _select_candidates(
        self,
        event: str,
        pool_data: Any,
        context: Dict[str, Any]
    ) -> List[str]:
        """Dispatches pool selection using rich context (time, day of week, streaks, escalation)."""
        if isinstance(pool_data, list):
            return pool_data

        if not isinstance(pool_data, dict):
            return [str(pool_data)] if pool_data else []

        now_dt = datetime.datetime.now()

        # 1. Unlock Greetings: check quick unlock, day of week, then time of day
        if event == "unlock_greeting":
            if context.get("quick_unlock") and "quick_unlock" in pool_data:
                return pool_data["quick_unlock"]

            # Day of week nuances (Monday, Friday, Weekend)
            weekday = now_dt.weekday()
            if weekday == 0 and "monday" in pool_data and now_dt.hour < 12:
                return pool_data["monday"]
            if weekday == 4 and "friday" in pool_data and now_dt.hour >= 12:
                return pool_data["friday"]
            if weekday >= 5 and "weekend" in pool_data:
                return pool_data["weekend"]

            hour = now_dt.hour
            if 5 <= hour < 12 and "morning" in pool_data:
                return pool_data["morning"]
            if 12 <= hour < 17 and "afternoon" in pool_data:
                return pool_data["afternoon"]
            if 17 <= hour < 21 and "evening" in pool_data:
                return pool_data["evening"]
            if "night" in pool_data:
                return pool_data["night"]

        # 2. Late Night: select based on escalation level
        if event == "late_night":
            level = context.get("late_night_level", 1)
            level_key = f"level_{min(3, max(1, level))}"
            if level_key in pool_data:
                return pool_data[level_key]

        # Flatten any nested dictionary values if key matching was exhausted
        flattened: List[str] = []
        for v in pool_data.values():
            if isinstance(v, list):
                flattened.extend(v)
            elif isinstance(v, str):
                flattened.append(v)
        return flattened

    def _render_template(self, text: str, context: Dict[str, Any], persona: Dict[str, Any]) -> str:
        """Safely fills placeholders like {name}, {time}, {weather}, {repo}, {task_count}."""
        address_terms = persona.get("address_terms", ["Sir"])
        default_name = context.get("user_name") or address_terms[0]

        placeholders: Dict[str, Any] = {
            "name": context.get("name") or default_name,
            "title": context.get("title") or default_name,
            "time": context.get("time") or datetime.datetime.now().strftime("%I:%M %p"),
            "weather": context.get("weather", "fair weather"),
            "task_count": context.get("task_count", 0),
            "repo": context.get("repo", "workspace"),
            "uncommitted": context.get("uncommitted", 0),
            "unpushed": context.get("unpushed", 0),
            "session_hours": f"{context.get('session_hours', 1.0):.1f}"
        }

        # Safe regex substitution for any {key} to prevent KeyError
        def _replace_placeholder(match: re.Match) -> str:
            k = match.group(1)
            return str(placeholders.get(k, match.group(0)))

        rendered = re.sub(r"\{(\w+)\}", _replace_placeholder, text)
        return rendered.strip()


# Global Singleton Engine Instance
personality_engine = PersonaEngine()
