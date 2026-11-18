"""Event-driven reminder scheduler with persistent state and monotonic safety.

Guarantees:
- Exactly-once execution: persists last_fired per rule_id in scheduler_state.json.
- Missed-event policy: <= 120s overdue fires; > 120s is skipped.
- System wake/unlock safety: fires at most ONE reminder after sleep, never a burst.
- Midnight-crossing windows: robust window evaluation and efficient sleep calculation.
- Hydration: 30-45 min random jitter, weekday work-hours only, rollovers to next workday.
- Monotonic & wall-clock jump safety: realigns schedule on clock/timezone/DST shifts.
"""

from dataclasses import dataclass, field
import heapq
import json
import logging
import os
from pathlib import Path
import random
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .voice_engine import SpeechPriority, VoiceEngine

logger = logging.getLogger("MacAssistant.Scheduler")

MAX_OVERDUE_SECONDS = 120.0  # 2 minutes: fire if overdue <= 120s, skip if older

DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "MacAssistant"
FALLBACK_STATE_DIR = Path(__file__).resolve().parent.parent / "data"


def get_state_file_path() -> Path:
    """Resolves the scheduler state file path with safe sandboxing fallback."""
    try:
        DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_STATE_DIR / "scheduler_state.json"
    except Exception:
        FALLBACK_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return FALLBACK_STATE_DIR / "scheduler_state.json"


def in_window(dt: datetime, start_h: int, end_h: int) -> bool:
    """Checks whether dt's hour falls within [start_h, end_h).
    Correctly handles midnight-crossing windows (e.g. 22:00 to 05:00).
    """
    h = dt.hour
    if start_h == end_h:
        return True
    if start_h < end_h:
        return start_h <= h < end_h
    # start_h > end_h (crosses midnight)
    return h >= start_h or h < end_h


def next_window_start(dt: datetime, start_h: int) -> datetime:
    """Computes the next datetime when hour reaches start_h."""
    target = dt.replace(hour=start_h, minute=0, second=0, microsecond=0)
    if target <= dt:
        target += timedelta(days=1)
    return target


@dataclass(order=True)
class ScheduledRule:
    due_epoch: float
    rule_id: str = field(compare=False)
    handler: Callable[[Dict[str, Any]], None] = field(compare=False)


class ReminderScheduler:
    """Evaluates time rules using an event-driven priority heap with persistence."""

    def __init__(self, voice_engine: VoiceEngine):
        self.engine = voice_engine
        self._heap: List[ScheduledRule] = []
        self._last_config: Dict[str, Any] = {}
        self._state_file = get_state_file_path()
        self._state: Dict[str, Any] = self._load_state()
        self._last_monotonic = time.monotonic()
        self._last_wall_time = time.time()

    def _load_state(self) -> Dict[str, Any]:
        """Loads persistent state atomically from disk."""
        if self._state_file.exists():
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to read scheduler_state.json (%s). Starting clean.", e)
        return {"last_fired_dates": {}, "last_fired_timestamps": {}}

    def _save_state(self) -> None:
        """Persists state atomically via temporary file and os.replace."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=str(self._state_file.parent), prefix="sched_state_", suffix=".tmp"
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
            os.replace(temp_path, self._state_file)
        except Exception as e:
            logger.error("Failed to write scheduler_state.json atomically: %s", e)

    def _record_fired(self, rule_id: str, ts: Optional[float] = None) -> None:
        """Records the timestamp and current date for a fired rule."""
        if ts is None:
            ts = time.time()
        today_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        self._state.setdefault("last_fired_dates", {})[rule_id] = today_str
        self._state.setdefault("last_fired_timestamps", {})[rule_id] = ts
        self._save_state()

    def was_fired_today(self, rule_id: str, now_dt: Optional[datetime] = None) -> bool:
        """Checks if a rule was already recorded as fired today."""
        if now_dt is None:
            now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")
        return self._state.get("last_fired_dates", {}).get(rule_id) == today_str

    def get_last_fired_timestamp(self, rule_id: str) -> float:
        """Returns the epoch timestamp of when the rule was last fired."""
        return float(self._state.get("last_fired_timestamps", {}).get(rule_id, 0.0))

    def seconds_until_next_event(self, max_cap: float = 10.0) -> float:
        """Returns seconds until the next due event, checking for clock/DST jumps."""
        now_mono = time.monotonic()
        now_wall = time.time()

        # Detect wall-clock jumps (> 60s discrepancy with monotonic)
        mono_delta = now_mono - self._last_monotonic
        wall_delta = now_wall - self._last_wall_time
        if abs(wall_delta - mono_delta) > 60.0:
            logger.info("Clock jump or DST shift detected (delta=%.1fs). Re-syncing schedule.", wall_delta - mono_delta)
            if self._last_config:
                self.rebuild_schedule(self._last_config)

        self._last_monotonic = now_mono
        self._last_wall_time = now_wall

        if not self._heap:
            return max_cap

        diff = self._heap[0].due_epoch - now_wall
        if diff <= 0:
            return 0.0
        return min(diff, max_cap)

    def rebuild_schedule(self, config: Dict[str, Any]) -> None:
        """Recomputes all periodic and daily fixed events into the heap."""
        self._last_config = config
        now = time.time()
        now_dt = datetime.now()
        self._heap.clear()

        # 1. Fixed Daily Scheduled Reminders (11:00, 13:00, 16:00, 18:18, etc.)
        for reminder in config.get("scheduled_reminders", []):
            time_str = reminder.get("time")
            if not time_str:
                continue
            rule_id = f"daily_{time_str}"
            due = self._compute_next_daily_epoch(time_str, rule_id)
            heapq.heappush(
                self._heap,
                ScheduledRule(
                    due_epoch=due,
                    rule_id=rule_id,
                    handler=self._make_daily_handler(reminder, time_str, rule_id)
                )
            )

        # 2. 20-20-20 Eye break (every 20 min)
        eye_cfg = config.get("eye_break_reminders", {})
        if eye_cfg.get("enabled", True):
            interval_secs = eye_cfg.get("interval_minutes", 20) * 60
            last_ts = self.get_last_fired_timestamp("eye_break")
            due = max(now + 10.0, (last_ts + interval_secs) if last_ts > 0 else (now + interval_secs))
            heapq.heappush(
                self._heap,
                ScheduledRule(
                    due_epoch=due,
                    rule_id="eye_break",
                    handler=self._handle_eye_break
                )
            )

        # 3. Hydration check (30-45 min jitter, Mon-Fri work hours only)
        hydro_cfg = config.get("hydration_reminders", {})
        if hydro_cfg.get("enabled", True):
            due = self._compute_next_hydration_epoch(now_dt, hydro_cfg)
            heapq.heappush(
                self._heap,
                ScheduledRule(
                    due_epoch=due,
                    rule_id="hydration",
                    handler=self._handle_hydration
                )
            )

        # 4. Late-night guardian (every 30 min, 22:00-05:00)
        late_cfg = config.get("late_night_reminders", {})
        if late_cfg.get("enabled", False):
            due = self._compute_next_late_night_epoch(now_dt, late_cfg)
            heapq.heappush(
                self._heap,
                ScheduledRule(
                    due_epoch=due,
                    rule_id="late_night",
                    handler=self._handle_late_night
                )
            )

        logger.debug("Rebuilt scheduler heap with %d scheduled rules.", len(self._heap))

    def on_system_wake(self, config: Dict[str, Any]) -> None:
        """Called when system wakes from sleep or unlocks to prevent burst reminders.
        Drops sleep backlog and guarantees at most ONE relevant reminder fires.
        """
        logger.info("System wake/unlock detected. Handling backlog safely.")
        now = time.time()

        # Find any due items currently on the heap
        overdue_rules: List[ScheduledRule] = []
        while self._heap and self._heap[0].due_epoch <= now:
            overdue_rules.append(heapq.heappop(self._heap))

        # Filter out anything overdue by > 120s
        valid_overdue = [r for r in overdue_rules if (now - r.due_epoch) <= MAX_OVERDUE_SECONDS]

        # Re-sync schedule from fresh state
        self.rebuild_schedule(config)

        if valid_overdue:
            # Pick at most ONE reminder to fire (prefer daily alerts over eye/hydration)
            def _rank(r: ScheduledRule) -> int:
                if r.rule_id.startswith("daily_"):
                    return 1
                if r.rule_id == "late_night":
                    return 2
                if r.rule_id == "hydration":
                    return 3
                return 4

            valid_overdue.sort(key=_rank)
            chosen = valid_overdue[0]
            logger.info("Wake backlog: firing single chosen reminder '%s' and discarding remainder.", chosen.rule_id)
            try:
                chosen.handler(config)
            except Exception as e:
                logger.error("Error executing wake reminder '%s': %s", chosen.rule_id, e)

    def process_due_events(self, config: Dict[str, Any]) -> bool:
        """Pops and executes due rules on the heap. Returns True if speech occurred."""
        now = time.time()
        spoken = False

        while self._heap and self._heap[0].due_epoch <= now:
            rule = heapq.heappop(self._heap)

            # Check if overdue by more than 2 minutes (120s)
            overdue_by = now - rule.due_epoch
            if overdue_by > MAX_OVERDUE_SECONDS:
                logger.info("Skipping stale reminder '%s' overdue by %.1f seconds.", rule.rule_id, overdue_by)
                self._reschedule_rule(rule, config)
                continue

            # Prevent re-firing daily alerts if already fired today
            if rule.rule_id.startswith("daily_") and self.was_fired_today(rule.rule_id):
                logger.info("Daily reminder '%s' already fired today. Rescheduling for tomorrow.", rule.rule_id)
                self._reschedule_rule(rule, config)
                continue

            try:
                rule.handler(config)
                spoken = True
            except Exception as e:
                logger.error("Error executing scheduler rule '%s': %s", rule.rule_id, e)

            # Re-enqueue next recurrence
            self._reschedule_rule(rule, config)

        return spoken

    def _reschedule_rule(self, rule: ScheduledRule, config: Dict[str, Any]) -> None:
        """Calculates next epoch for recurring rules and enqueues onto heap."""
        now = time.time()
        now_dt = datetime.now()

        if rule.rule_id.startswith("daily_"):
            time_str = rule.rule_id.replace("daily_", "")
            next_due = self._compute_next_daily_epoch(time_str, rule.rule_id, advance_if_today=True)
            heapq.heappush(self._heap, ScheduledRule(due_epoch=next_due, rule_id=rule.rule_id, handler=rule.handler))

        elif rule.rule_id == "eye_break":
            eye_cfg = config.get("eye_break_reminders", {})
            if eye_cfg.get("enabled", True):
                interval = eye_cfg.get("interval_minutes", 20) * 60
                heapq.heappush(self._heap, ScheduledRule(due_epoch=now + interval, rule_id=rule.rule_id, handler=rule.handler))

        elif rule.rule_id == "hydration":
            hydro_cfg = config.get("hydration_reminders", {})
            if hydro_cfg.get("enabled", True):
                next_due = self._compute_next_hydration_epoch(now_dt, hydro_cfg)
                heapq.heappush(self._heap, ScheduledRule(due_epoch=next_due, rule_id=rule.rule_id, handler=rule.handler))

        elif rule.rule_id == "late_night":
            late_cfg = config.get("late_night_reminders", {})
            if late_cfg.get("enabled", False):
                next_due = self._compute_next_late_night_epoch(now_dt, late_cfg)
                heapq.heappush(self._heap, ScheduledRule(due_epoch=next_due, rule_id=rule.rule_id, handler=rule.handler))

    def _compute_next_daily_epoch(self, time_str: str, rule_id: str, advance_if_today: bool = False) -> float:
        """Calculates next timestamp for HH:MM daily reminder, respecting already fired status."""
        now = datetime.now()
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
        except (ValueError, IndexError):
            logger.warning("Invalid time format '%s' for rule '%s'. Defaulting to 1 hour.", time_str, rule_id)
            return time.time() + 3600.0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If already fired today, or if target time has already passed today, push to tomorrow
        if advance_if_today or target <= now or self.was_fired_today(rule_id, now):
            target += timedelta(days=1)

        return target.timestamp()

    def _compute_next_hydration_epoch(self, now_dt: datetime, hydro_cfg: Dict[str, Any]) -> float:
        """Calculates next due epoch for hydration (30-45 min jitter, Mon-Fri work hours only)."""
        start_hour = hydro_cfg.get("start_hour", 9)
        end_hour = hydro_cfg.get("end_hour", 18)  # standard 9:00 - 18:00
        min_interval = hydro_cfg.get("min_interval_minutes", 30)
        max_interval = hydro_cfg.get("max_interval_minutes", 45)

        # Check if today is a weekday (0=Mon, 4=Fri) and within work hours
        is_weekday = now_dt.weekday() < 5
        in_work_hours = is_weekday and (start_hour <= now_dt.hour < end_hour)

        if in_work_hours:
            jitter_seconds = random.randint(min_interval * 60, max_interval * 60)
            candidate_dt = now_dt + timedelta(seconds=jitter_seconds)
            # If candidate overflows end_hour, advance to next workday
            if candidate_dt.hour >= end_hour:
                return self._rollover_workday(now_dt, start_hour).timestamp()
            return candidate_dt.timestamp()

        # Outside work hours or on weekend -> rollover to next workday start_hour
        return self._rollover_workday(now_dt, start_hour).timestamp()

    def _rollover_workday(self, from_dt: datetime, start_hour: int) -> datetime:
        """Finds the next Monday-Friday date starting at start_hour."""
        target = from_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        if target <= from_dt:
            target += timedelta(days=1)
        # Advance through weekends (5=Sat, 6=Sun)
        while target.weekday() >= 5:
            target += timedelta(days=1)
        return target

    def _compute_next_late_night_epoch(self, now_dt: datetime, late_cfg: Dict[str, Any]) -> float:
        """Calculates next epoch for late night rest guardian (22:00-05:00 window)."""
        start_h = late_cfg.get("start_hour", 22)
        end_h = late_cfg.get("end_hour", 5)
        interval_min = late_cfg.get("interval_minutes", 30)

        if in_window(now_dt, start_h, end_h):
            # Currently in window: schedule next interval (30 min)
            return (now_dt + timedelta(minutes=interval_min)).timestamp()

        # Outside late-night window: sleep directly until start_h (e.g. 22:00 tonight)
        target = next_window_start(now_dt, start_h)
        return target.timestamp()

    def _make_daily_handler(self, reminder: Dict[str, Any], time_str: str, rule_id: str) -> Callable[[Dict[str, Any]], None]:
        def _handler(cfg: Dict[str, Any]) -> None:
            self._record_fired(rule_id)
            persona_key = cfg.get("assistant_persona", "friday").lower()
            name = cfg.get("user_name", "Sir")
            template = reminder.get(f"{persona_key}_message") or reminder.get("message")
            if template:
                msg = template.format(name=name, title=name)
                logger.info("Triggering scheduled reminder (%s): %s", time_str, msg)
                self.engine.speak(msg, cfg, priority=SpeechPriority.REMINDER)
        return _handler

    def _handle_eye_break(self, cfg: Dict[str, Any]) -> None:
        eye_cfg = cfg.get("eye_break_reminders", {})
        if not eye_cfg.get("enabled", True):
            return
        self._record_fired("eye_break")
        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = eye_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering 20-20-20 eye break reminder: %s", msg)
            self.engine.speak(msg, cfg, priority=SpeechPriority.REMINDER)

    def _handle_hydration(self, cfg: Dict[str, Any]) -> None:
        hydro_cfg = cfg.get("hydration_reminders", {})
        if not hydro_cfg.get("enabled", True):
            return

        now_dt = datetime.now()
        start_hour = hydro_cfg.get("start_hour", 9)
        end_hour = hydro_cfg.get("end_hour", 18)

        if now_dt.weekday() >= 5 or not (start_hour <= now_dt.hour < end_hour):
            return

        self._record_fired("hydration")
        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = hydro_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering hydration reminder: %s", msg)
            self.engine.speak(msg, cfg, priority=SpeechPriority.REMINDER)

    def _handle_late_night(self, cfg: Dict[str, Any]) -> None:
        late_cfg = cfg.get("late_night_reminders", {})
        if not late_cfg.get("enabled", False):
            return

        now_dt = datetime.now()
        start_h = late_cfg.get("start_hour", 22)
        end_h = late_cfg.get("end_hour", 5)

        if not in_window(now_dt, start_h, end_h):
            return

        self._record_fired("late_night")
        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = late_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering late night rest reminder: %s", msg)
            self.engine.speak(msg, cfg, priority=SpeechPriority.REMINDER)
