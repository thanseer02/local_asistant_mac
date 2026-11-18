"""Persona Engine, Context Resolver, Mood & Escalation System, and Multi-Boot Session Selector.

Features:
- Dynamic persona selection on system boot or new login session.
- No immediate repeats: persists last N personas in persona_state.json atomically.
- Weighted randomness, recency-boost for least-used personas, and time-aware bias.
- Verification of installed macOS voices (`say -v '?'`) to exclude personas with missing voices.
- Session detection: checks OS boot epoch (`sysctl kern.boottime`) and console session ID (`SECURITYSESSIONID`).
- Crash/launchd relaunch preservation: maintains current persona within the same session.
- Modes supported: random (default), rotate, fixed.
- CLI overrides: `--reroll` and `--persona <id>`.
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
import subprocess
import tempfile
import time
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("MacAssistant.Personality")

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"
FALLBACK_PERSONA_ID = "friday"

DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "MacAssistant"
FALLBACK_STATE_DIR = Path(__file__).resolve().parent.parent / "data"


def get_persona_state_path() -> Path:
    """Resolves persona_state.json path with sandbox fallback."""
    try:
        DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_STATE_DIR / "persona_state.json"
    except Exception:
        FALLBACK_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return FALLBACK_STATE_DIR / "persona_state.json"


_INSTALLED_VOICES_CACHE: Optional[Set[str]] = None


def get_installed_voices() -> Set[str]:
    """Inspects native macOS `say -v '?'` to discover all installed voices with in-memory caching."""
    global _INSTALLED_VOICES_CACHE
    if _INSTALLED_VOICES_CACHE is not None:
        return _INSTALLED_VOICES_CACHE

    installed = set()
    try:
        res = subprocess.run(["/usr/bin/say", "-v", "?"], capture_output=True, text=True, timeout=2.0)
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts:
                installed.add(parts[0].strip().lower())
    except Exception as e:
        logger.warning("Could not probe installed macOS voices (%s). Falling back to permissive voice list.", e)
        installed = {"daniel", "moira", "ralph", "tessa", "fred", "junior", "kathy", "whisper", "samantha", "alex"}

    _INSTALLED_VOICES_CACHE = installed
    return _INSTALLED_VOICES_CACHE


def get_system_boot_epoch() -> int:
    """Extracts integer boot seconds from `sysctl kern.boottime`."""
    try:
        res = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=1.0)
        out = res.stdout.strip()
        m = re.search(r"sec = (\d+)", out)
        if m:
            return int(m.group(1))
    except Exception as e:
        logger.debug("Failed sysctl kern.boottime query: %s", e)
    return 0


def get_current_session_id() -> str:
    """Retrieves console user session identifier from environment."""
    return os.environ.get("SECURITYSESSIONID") or os.environ.get("LaunchInstanceID") or "default_session"


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
        """Decays heightened moods back to calm over 45 minutes."""
        now = time.time()
        elapsed = now - self.last_update_ts
        today_str = datetime.date.today().isoformat()

        if self.daily_fired_date != today_str:
            self.daily_fired_date = today_str
            self.daily_easter_eggs_fired.clear()
            self.consecutive_late_night_nudges = 0
            self.first_unlock_today = None

        if elapsed > 2700:
            if self.current_mood != "calm":
                logger.debug("Mood decayed from %s back to calm after %.1f min.", self.current_mood, elapsed / 60)
                self.current_mood = "calm"
                self.consecutive_ignored_reminders = 0
            self.last_update_ts = now


class PersonaEngine:
    """Core personality system handling session selection, dialogues, mood, and context."""

    def __init__(self):
        self._personas: Dict[str, Dict[str, Any]] = {}
        self._recent_picks: Dict[str, Deque[str]] = {}
        self._history_window = 6
        self._mood_state = PersonaMoodState()
        self._state_file = get_persona_state_path()
        self._session_persona_id: Optional[str] = None
        self._is_new_session: bool = False
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

    def _load_persona_state(self) -> Dict[str, Any]:
        """Loads persistent persona state tracking boot epoch, session id, and history."""
        if self._state_file.exists():
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to parse persona_state.json (%s). Starting clean.", e)
        return {
            "current_persona": "friday",
            "history": [],
            "last_boot_sec": 0,
            "last_session_id": "",
            "last_used_timestamps": {}
        }

    def _save_persona_state(self, state: Dict[str, Any]) -> None:
        """Saves persona state atomically using tempfile and os.replace."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=str(self._state_file.parent), prefix="persona_state_", suffix=".tmp"
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(temp_path, self._state_file)
        except Exception as e:
            logger.error("Failed to write persona_state.json atomically: %s", e)

    def initialize_session(self, config: Dict[str, Any], force_reroll: bool = False, force_persona: Optional[str] = None) -> str:
        """Determines the active persona for this login or boot session.

        - If force_persona is provided: locks to that persona.
        - If force_reroll or new boot/session: rolls a new persona and persists state.
        - If daemon crashed or relaunched within same session: preserves current persona.
        """
        self.reload_personas()
        state = self._load_persona_state()

        if force_persona:
            pid = force_persona.lower().strip()
            if pid in self._personas:
                self._session_persona_id = pid
                state["current_persona"] = pid
                self._save_persona_state(state)
                logger.info("Forced persona set to '%s'.", pid)
                return pid

        current_boot = get_system_boot_epoch()
        current_sess = get_current_session_id()

        stored_boot = state.get("last_boot_sec", 0)
        stored_sess = state.get("last_session_id", "")
        stored_persona = state.get("current_persona")

        is_new_boot = (current_boot > 0 and current_boot != stored_boot)
        is_new_login = (current_sess and current_sess != stored_sess)

        if force_reroll or is_new_boot or is_new_login or not stored_persona or stored_persona not in self._personas:
            logger.info("New boot (%s) or login session detected (boot=%d, sess=%s). Rolling persona...",
                        is_new_boot, current_boot, current_sess)
            chosen = self.select_persona_for_session(config, state)
            self._session_persona_id = chosen
            self._is_new_session = True

            # Update history
            hist = state.get("history", [])
            hist.append(chosen)
            max_hist = config.get("persona_history_size", 3)
            state["history"] = hist[-max_hist:]
            state["current_persona"] = chosen
            state["last_boot_sec"] = current_boot
            state["last_session_id"] = current_sess
            state.setdefault("last_used_timestamps", {})[chosen] = time.time()
            self._save_persona_state(state)
            logger.info("Selected persona '%s' for this session.", chosen)
            return chosen

        # Same session (e.g. launchd relaunch or daemon restart) -> keep consistent
        self._session_persona_id = stored_persona
        self._is_new_session = False
        logger.info("Preserving existing session persona '%s' (same boot/session).", stored_persona)
        return stored_persona

    def select_persona_for_session(self, config: Dict[str, Any], state: Dict[str, Any]) -> str:
        """Selects a persona according to mode (random, rotate, fixed), weights, and history."""
        mode = config.get("persona_mode", "random").lower().strip()
        if mode not in ("random", "rotate", "fixed"):
            logger.warning("Invalid persona_mode '%s'. Falling back to 'random'.", mode)
            mode = "random"

        # Fixed mode
        if mode == "fixed":
            target = (config.get("persona") or config.get("assistant_persona") or "friday").lower()
            if target in self._personas:
                return target
            return FALLBACK_PERSONA_ID

        # Filter installed voices
        installed_voices = get_installed_voices()
        available_pool = []
        configured_pool = config.get("persona_pool") or []
        configured_pool = [p.lower() for p in configured_pool]

        for pid, data in self._personas.items():
            if configured_pool and pid not in configured_pool:
                continue
            voice = (data.get("voice") or "").lower()
            if installed_voices and voice and voice not in installed_voices:
                logger.info("Persona '%s' excluded because voice '%s' is not installed.", pid, voice)
                continue
            available_pool.append(pid)

        if not available_pool:
            logger.warning("No personas have installed voices available. Defaulting to '%s'.", FALLBACK_PERSONA_ID)
            return FALLBACK_PERSONA_ID

        # Rotate mode
        if mode == "rotate":
            available_pool.sort()
            last = state.get("current_persona")
            if last in available_pool:
                idx = (available_pool.index(last) + 1) % len(available_pool)
                return available_pool[idx]
            return available_pool[0]

        # Random mode with history exclusions and weighted probability
        history = state.get("history", [])
        history_size = max(1, config.get("persona_history_size", 3))

        # Exclude recent personas unless pool is smaller than history size
        candidates = [p for p in available_pool if p not in history[-history_size:]]
        if not candidates:
            candidates = available_pool

        # Calculate weights
        weights_cfg = config.get("persona_weights", {})
        now_dt = datetime.datetime.now()
        hour = now_dt.hour
        is_friday = (now_dt.weekday() == 4)
        last_used = state.get("last_used_timestamps", {})

        weighted_candidates: List[float] = []
        for p in candidates:
            w = float(weights_cfg.get(p, 1.0))

            # Recency boost: boost personas unused for the longest time
            time_since_used = time.time() - float(last_used.get(p, 0.0))
            if time_since_used > 86400:  # > 24 hours
                w += 0.5

            # Time-aware bias
            if hour >= 22 or hour < 6:
                # Calmer personas favored late night
                if p in ("zen", "sleepy", "alfred"):
                    w *= 1.8
                elif p in ("coach", "sarcastic"):
                    w *= 0.5
            elif 6 <= hour < 12:
                # Energetic personas favored morning
                if p in ("coach", "friday", "jarvis"):
                    w *= 1.4

            if is_friday and p in ("coach", "friday", "pirate"):
                w *= 1.5

            weighted_candidates.append(max(0.1, w))

        chosen = random.choices(candidates, weights=weighted_candidates, k=1)[0]
        return chosen

    def get_session_persona(self, config: Dict[str, Any]) -> str:
        """Returns the established session persona ID, initializing if needed."""
        if not self._session_persona_id:
            return self.initialize_session(config)
        return self._session_persona_id

    def get_persona(self, persona_id: str) -> Dict[str, Any]:
        """Returns the persona definition, safely falling back to friday or first available."""
        pid = (persona_id or "").lower().strip()
        if pid in self._personas:
            return self._personas[pid]
        self.reload_personas()
        if pid in self._personas:
            return self._personas[pid]
        if FALLBACK_PERSONA_ID in self._personas:
            return self._personas[FALLBACK_PERSONA_ID]
        if self._personas:
            return next(iter(self._personas.values()))

        return {
            "id": "friday",
            "name": "Friday",
            "voice": "Moira",
            "base_rate": 172,
            "address_terms": ["Sir"],
            "line_pools": {}
        }

    def record_unlock(self) -> Tuple[bool, float]:
        """Tracks unlock events. Returns (is_quick_unlock, continuous_session_hours)."""
        now = time.time()
        self._mood_state.decay()

        if self._mood_state.first_unlock_today is None:
            self._mood_state.first_unlock_today = now

        last = self._mood_state.last_unlock_ts
        self._mood_state.last_unlock_ts = now

        quick_unlock = (last > 0 and (now - last) < 120.0)
        session_hours = max(0.0, (now - self._mood_state.first_unlock_today) / 3600.0)
        self._mood_state.consecutive_ignored_reminders = 0

        return quick_unlock, session_hours

    def record_reminder_fired(self) -> int:
        """Tracks consecutive reminder firings to calculate escalation levels."""
        self._mood_state.decay()
        self._mood_state.consecutive_ignored_reminders += 1
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
        """Picks a witty, non-repeating line for the current session persona and calculates speech rate."""
        if context is None:
            context = {}
        if config is None:
            config = {}

        persona_id = self.get_session_persona(config)
        persona = self.get_persona(persona_id)
        personality_cfg = config.get("personality", {})

        humor_level = personality_cfg.get("humor_level", 2)
        easter_eggs_enabled = personality_cfg.get("easter_eggs", True)
        self._mood_state.decay()

        # Rare 3% easter eggs
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
            fallback_text = f"Welcome back, {context.get('name', 'Sir')}."
            return fallback_text, persona.get("base_rate", 170)

        history_key = f"{persona['id']}_{event}"
        if history_key not in self._recent_picks:
            self._recent_picks[history_key] = deque(maxlen=self._history_window)

        recent = self._recent_picks[history_key]
        filtered = [c for c in candidates if c not in recent]
        chosen = random.choice(filtered) if filtered else random.choice(candidates)
        recent.append(chosen)

        mood = self._mood_state.current_mood
        mood_cfg = persona.get("mood_tuning", {}).get(mood, {"rate_offset": 0, "pitch_mod": ""})
        rate_offset = mood_cfg.get("rate_offset", 0)
        pitch_mod = mood_cfg.get("pitch_mod", "")

        adjusted_rate = max(130, min(220, persona.get("base_rate", 170) + rate_offset))
        rendered_text = self._render_template(chosen, context, persona)

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

        if event == "unlock_greeting":
            if context.get("quick_unlock") and "quick_unlock" in pool_data:
                return pool_data["quick_unlock"]

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

        if event == "late_night":
            level = context.get("late_night_level", 1)
            level_key = f"level_{min(3, max(1, level))}"
            if level_key in pool_data:
                return pool_data[level_key]

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

        def _replace_placeholder(match: re.Match) -> str:
            k = match.group(1)
            return str(placeholders.get(k, match.group(0)))

        rendered = re.sub(r"\{(\w+)\}", _replace_placeholder, text)
        return rendered.strip()

    def build_system_prompt(
        self,
        config: Optional[Dict[str, Any]] = None,
        persona_id: Optional[str] = None
    ) -> str:
        """Constructs a spoken-optimized conversational LLM system prompt for the active persona."""
        cfg = config or {}
        pid = persona_id or self.get_session_persona(cfg)
        persona = self.get_persona(pid)

        name = persona.get("name", "Assistant")
        address_terms = persona.get("address_terms", ["Sir"])
        user_name = cfg.get("user_name", address_terms[0])
        style = persona.get("style_notes", "Helpful, natural and conversational voice assistant.")

        prompt = f"""You are {name}, a personal voice assistant speaking aloud to {user_name}.
Everything you write will be converted to speech, so write exactly how a person talks, not how they write.

Rules:
- Keep replies to 1-3 short sentences unless asked for detail.
- Use contractions (it's, you've, I'll) and casual phrasing.
- Never use markdown, bullets, emojis, asterisks, code blocks, or URLs.
- Write numbers, times, and units as spoken: "seven thirty in the evening", "twenty-two degrees", not "19:30" or "22°C".
- Spell out abbreviations: "Doctor", "versus", "for example".
- Use natural fillers sparingly and only when it fits: "hmm", "ohh", "alright", "let me see". At most one per reply, never in simple confirmations.
- Use commas and ellipses for natural pauses. Use "..." for a thinking beat.
- React before answering when appropriate: "Oh, nice.", "Hmm, that's odd."
- Vary your wording. Never open two replies in a row the same way.
- Stay in character: {style}
"""
        return prompt.strip()


# Global Singleton Engine Instance
personality_engine = PersonaEngine()
