"""Event-driven reminder scheduler with priority heap (heapq).

Replaces string timestamp polling with an event queue:
- Computes next due epoch for 20-20-20, hydration (random jitter, work hours only),
  fixed clock alerts (11:00, 13:00, 16:00, 18:18), and late-night guardian.
- Provides `seconds_until_next_event(max_cap=10.0)` for the main loop's select() timeout,
  allowing the process to sleep until work exists.
- Rebuilds heap on config hot-reload and after system wake.
- Discards any event overdue by more than 5 minutes to prevent burst alerts after sleep.
"""

from dataclasses import dataclass, field
import heapq
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .voice_engine import SpeechPriority, VoiceEngine

logger = logging.getLogger("MacAssistant.Scheduler")

MAX_OVERDUE_SECONDS = 300.0  # 5 minutes: skip anything older than this after system sleep


@dataclass(order=True)
class ScheduledRule:
    due_epoch: float
    rule_id: str = field(compare=False)
    handler: Callable[[Dict[str, Any]], None] = field(compare=False)


class ReminderScheduler:
    """Evaluates time rules using an event-driven priority heap (heapq)."""

    def __init__(self, voice_engine: VoiceEngine):
        self.engine = voice_engine
        self._heap: List[ScheduledRule] = []
        self._last_config: Dict[str, Any] = {}
        self._last_eye_break: float = 0.0
        self._last_hydration: float = 0.0
        self._last_late_night: float = 0.0

    def seconds_until_next_event(self, max_cap: float = 10.0) -> float:
        """Returns seconds until the next due event on the heap, capped at max_cap."""
        now = time.time()
        if not self._heap:
            return max_cap

        earliest = self._heap[0].due_epoch
        diff = earliest - now
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
            time_str = reminder.get("time")  # e.g. "11:00", "13:00"
            if not time_str:
                continue
            due = self._compute_next_daily_epoch(time_str)
            heapq.heappush(
                self._heap,
                ScheduledRule(
                    due_epoch=due,
                    rule_id=f"daily_{time_str}",
                    handler=self._make_daily_handler(reminder, time_str)
                )
            )

        # 2. 20-20-20 Eye break
        eye_cfg = config.get("eye_break_reminders", {})
        if eye_cfg.get("enabled", True):
            interval_secs = eye_cfg.get("interval_minutes", 20) * 60
            due = now + interval_secs
            heapq.heappush(
                self._heap,
                ScheduledRule(
                    due_epoch=due,
                    rule_id="eye_break",
                    handler=self._handle_eye_break
                )
            )

        # 3. Hydration check (with 30-45 min random jitter, work hours only)
        hydro_cfg = config.get("hydration_reminders", {})
        if hydro_cfg.get("enabled", True):
            interval_min = hydro_cfg.get("interval_minutes", 45)
            # Apply +/- 5 min random jitter
            jittered_seconds = (interval_min * 60) + random.randint(-180, 180)
            due = now + max(300, jittered_seconds)
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
            interval_secs = late_cfg.get("interval_minutes", 30) * 60
            due = now + interval_secs
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
        """Called when system wakes from sleep to prevent burst firing of missed events."""
        logger.info("System wake detected. Rebuilding scheduler heap and dropping sleep backlog.")
        self.rebuild_schedule(config)

    def process_due_events(self, config: Dict[str, Any]) -> bool:
        """Pops and executes any due rules on the heap. Returns True if speech occurred."""
        now = time.time()
        spoken = False

        while self._heap and self._heap[0].due_epoch <= now:
            rule = heapq.heappop(self._heap)

            # Check if overdue by more than 5 minutes (e.g. system was sleeping)
            if now - rule.due_epoch > MAX_OVERDUE_SECONDS:
                logger.info("Skipping stale reminder '%s' overdue by %.1f minutes.", rule.rule_id, (now - rule.due_epoch) / 60)
                # Reschedule for tomorrow if daily, or next interval
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

        if rule.rule_id.startswith("daily_"):
            time_str = rule.rule_id.replace("daily_", "")
            next_due = self._compute_next_daily_epoch(time_str)
            heapq.heappush(self._heap, ScheduledRule(due_epoch=next_due, rule_id=rule.rule_id, handler=rule.handler))

        elif rule.rule_id == "eye_break":
            eye_cfg = config.get("eye_break_reminders", {})
            if eye_cfg.get("enabled", True):
                interval = eye_cfg.get("interval_minutes", 20) * 60
                heapq.heappush(self._heap, ScheduledRule(due_epoch=now + interval, rule_id=rule.rule_id, handler=rule.handler))

        elif rule.rule_id == "hydration":
            hydro_cfg = config.get("hydration_reminders", {})
            if hydro_cfg.get("enabled", True):
                interval_min = hydro_cfg.get("interval_minutes", 45)
                jittered = (interval_min * 60) + random.randint(-180, 180)
                heapq.heappush(self._heap, ScheduledRule(due_epoch=now + max(300, jittered), rule_id=rule.rule_id, handler=rule.handler))

        elif rule.rule_id == "late_night":
            late_cfg = config.get("late_night_reminders", {})
            if late_cfg.get("enabled", False):
                interval = late_cfg.get("interval_minutes", 30) * 60
                heapq.heappush(self._heap, ScheduledRule(due_epoch=now + interval, rule_id=rule.rule_id, handler=rule.handler))

    def _compute_next_daily_epoch(self, time_str: str) -> float:
        """Calculates next timestamp for HH:MM daily reminder."""
        now = datetime.now()
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            return time.time() + 3600.0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()

    def _make_daily_handler(self, reminder: Dict[str, Any], time_str: str) -> Callable[[Dict[str, Any]], None]:
        def _handler(cfg: Dict[str, Any]) -> None:
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
        end_hour = hydro_cfg.get("end_hour", 21)

        # Only trigger during working hours
        if not (start_hour <= now_dt.hour < end_hour):
            return

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
        current_hour = now_dt.hour

        is_late_night = (
            (current_hour >= start_h or current_hour < end_h)
            if start_h > end_h
            else (start_h <= current_hour < end_h)
        )

        if not is_late_night:
            return

        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = late_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering late night rest reminder: %s", msg)
            self.engine.speak(msg, cfg, priority=SpeechPriority.REMINDER)
