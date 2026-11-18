"""Scheduler for tea, lunch, go-home, late-night rest, 20-20-20 eye strain, and hydration alerts.

Uses a priority event queue (heapq) to sleep until the next due reminder or snooze,
eliminating CPU-polling loops.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import heapq
import logging
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("MacAssistant.Scheduler")


@dataclass(order=True)
class ScheduledEvent:
    due_time: float
    event_id: str = field(compare=False)
    callback: Callable[[], None] = field(compare=False)
    recurring_interval: Optional[float] = field(default=None, compare=False)


class ReminderScheduler:
    """Evaluates time rules and triggers audio alerts for wellness, health, and schedule.

    Uses an event heap + Condition variable so the background worker sleeps until
    the next scheduled event or until woken by new events / snooze requests.
    """

    def __init__(self, voice_engine: Any):
        self.engine = voice_engine
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._event_heap: List[ScheduledEvent] = []
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        # Tracking state
        self.last_checked_minute: Optional[str] = None
        self.last_late_night_time: float = 0
        self.last_eye_break_time: float = 0
        self.last_hydration_time: float = 0
        self.current_config: Dict[str, Any] = {}

        # DND / Busy suppressor callback (optional, injected in A7)
        self.is_busy_suppressed: Optional[Callable[[], bool]] = None

    def start(self, config: Dict[str, Any]) -> None:
        """Starts the event-driven scheduler thread."""
        with self._lock:
            self.current_config = config
            if self._running:
                return
            self._running = True
            self._rebuild_schedule_locked()
            self._worker_thread = threading.Thread(
                target=self._run_loop, name="MacAssistant-Scheduler", daemon=True
            )
            self._worker_thread.start()
            logger.info("Event-driven ReminderScheduler started.")

    def stop(self) -> None:
        """Stops the scheduler thread."""
        with self._lock:
            self._running = False
            self._cv.notify_all()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

    def update_config(self, config: Dict[str, Any]) -> None:
        """Hot-reloads configuration and recalculates next scheduled events."""
        with self._lock:
            self.current_config = config
            self._rebuild_schedule_locked()
            self._cv.notify_all()

    def add_custom_timer(self, delay_seconds: float, label: str, message: Optional[str] = None) -> None:
        """Adds a custom one-shot timer or reminder."""
        due = time.time() + max(1.0, delay_seconds)
        event_id = f"custom_timer_{int(due)}_{label}"

        def _fire():
            cfg = self.current_config
            msg = message or f"Timer complete: {label}."
            logger.info("Timer fired: %s", label)
            self.engine.speak(msg, cfg, priority="reminder")

        with self._lock:
            heapq.heappush(self._event_heap, ScheduledEvent(due, event_id, _fire, None))
            self._cv.notify_all()

    def snooze(self, minutes: int = 10, label: str = "reminder") -> None:
        """Snoozes the reminder for the given number of minutes."""
        self.add_custom_timer(
            delay_seconds=minutes * 60,
            label=f"Snoozed {label}",
            message=f"Reminder alert: You asked me to remind you in {minutes} minutes."
        )

    def _rebuild_schedule_locked(self) -> None:
        """Recomputes all periodic and daily fixed events into the heap."""
        now = time.time()
        self._event_heap.clear()

        config = self.current_config

        # 1. Fixed Daily Scheduled Reminders (Tea, lunch, wrap up, etc.)
        for reminder in config.get("scheduled_reminders", []):
            time_str = reminder.get("time")  # e.g. "11:00", "13:00"
            if not time_str:
                continue
            due = self._compute_next_daily_time(time_str)
            event_id = f"daily_{time_str}"
            heapq.heappush(
                self._event_heap,
                ScheduledEvent(
                    due_time=due,
                    event_id=event_id,
                    callback=self._make_daily_callback(reminder, time_str),
                    recurring_interval=86400.0,
                )
            )

        # 2. 20-20-20 Eye break
        eye_cfg = config.get("eye_break_reminders", {})
        if eye_cfg.get("enabled", True):
            interval_secs = eye_cfg.get("interval_minutes", 20) * 60
            due = now + interval_secs
            heapq.heappush(
                self._event_heap,
                ScheduledEvent(
                    due_time=due,
                    event_id="eye_break",
                    callback=self._fire_eye_break,
                    recurring_interval=float(interval_secs),
                )
            )

        # 3. Hydration check
        hydro_cfg = config.get("hydration_reminders", {})
        if hydro_cfg.get("enabled", True):
            interval_secs = hydro_cfg.get("interval_minutes", 30) * 60
            due = now + interval_secs
            heapq.heappush(
                self._event_heap,
                ScheduledEvent(
                    due_time=due,
                    event_id="hydration",
                    callback=self._fire_hydration,
                    recurring_interval=float(interval_secs),
                )
            )

        # 4. Late-night guardian check
        late_night_cfg = config.get("late_night_reminders", {})
        if late_night_cfg.get("enabled", True):
            interval_secs = late_night_cfg.get("interval_minutes", 30) * 60
            due = now + interval_secs
            heapq.heappush(
                self._event_heap,
                ScheduledEvent(
                    due_time=due,
                    event_id="late_night",
                    callback=self._fire_late_night,
                    recurring_interval=float(interval_secs),
                )
            )

    def _compute_next_daily_time(self, time_str: str) -> float:
        """Calculates next epoch timestamp for a daily HH:MM string."""
        now = datetime.now()
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            return time.time() + 3600.0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()

    def _make_daily_callback(self, reminder: Dict[str, Any], time_str: str) -> Callable[[], None]:
        def _cb():
            if self.is_busy_suppressed and self.is_busy_suppressed():
                logger.info("Suppressing daily reminder (%s) due to DND / active meeting.", time_str)
                return
            cfg = self.current_config
            persona_key = cfg.get("assistant_persona", "friday").lower()
            name = cfg.get("user_name", "Sir")
            template = reminder.get(f"{persona_key}_message") or reminder.get("message")
            if template:
                msg = template.format(name=name, title=name)
                logger.info("Triggering scheduled reminder (%s): %s", time_str, msg)
                self.engine.speak(msg, cfg, priority="reminder")
        return _cb

    def _fire_eye_break(self) -> None:
        if self.is_busy_suppressed and self.is_busy_suppressed():
            logger.debug("Suppressing eye break reminder: user in DND / meeting.")
            return
        cfg = self.current_config
        eye_cfg = cfg.get("eye_break_reminders", {})
        if not eye_cfg.get("enabled", True):
            return
        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = eye_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering 20-20-20 eye break: %s", msg)
            self.engine.speak(msg, cfg, priority="reminder")

    def _fire_hydration(self) -> None:
        if self.is_busy_suppressed and self.is_busy_suppressed():
            logger.debug("Suppressing hydration reminder: user in DND / meeting.")
            return
        cfg = self.current_config
        hydro_cfg = cfg.get("hydration_reminders", {})
        if not hydro_cfg.get("enabled", True):
            return
        now_dt = datetime.now()
        start_h = hydro_cfg.get("start_hour", 9)
        end_h = hydro_cfg.get("end_hour", 21)
        if not (start_h <= now_dt.hour < end_h):
            return
        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = hydro_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering hydration reminder: %s", msg)
            self.engine.speak(msg, cfg, priority="reminder")

    def _fire_late_night(self) -> None:
        if self.is_busy_suppressed and self.is_busy_suppressed():
            return
        cfg = self.current_config
        late_night_cfg = cfg.get("late_night_reminders", {})
        if not late_night_cfg.get("enabled", True):
            return
        now_dt = datetime.now()
        start_h = late_night_cfg.get("start_hour", 22)
        end_h = late_night_cfg.get("end_hour", 5)
        # Check night window
        is_late = (now_dt.hour >= start_h or now_dt.hour < end_h)
        if not is_late:
            return
        persona_key = cfg.get("assistant_persona", "friday").lower()
        name = cfg.get("user_name", "Sir")
        messages = late_night_cfg.get(f"{persona_key}_messages", [])
        if messages:
            msg = random.choice(messages).format(name=name, title=name)
            logger.info("Triggering late-night reminder: %s", msg)
            self.engine.speak(msg, cfg, priority="reminder")

    def _run_loop(self) -> None:
        """Event loop: sleeps until the nearest due event on the heap."""
        while True:
            with self._cv:
                if not self._running:
                    break

                now = time.time()
                timeout: Optional[float] = None

                if self._event_heap:
                    earliest = self._event_heap[0]
                    if earliest.due_time <= now:
                        event = heapq.heappop(self._event_heap)
                        # Re-schedule if recurring
                        if event.recurring_interval:
                            next_due = event.due_time + event.recurring_interval
                            # If fallen too far behind, schedule from now
                            if next_due <= now:
                                next_due = now + event.recurring_interval
                            heapq.heappush(
                                self._event_heap,
                                ScheduledEvent(next_due, event.event_id, event.callback, event.recurring_interval)
                            )
                        # Unlock before callback execution
                        self._lock.release()
                        try:
                            event.callback()
                        except Exception as e:
                            logger.error("Error running scheduled event callback (%s): %s", event.event_id, e)
                        finally:
                            self._lock.acquire()
                        continue
                    else:
                        timeout = earliest.due_time - now
                else:
                    timeout = None

                # Sleep until next event or until notified
                self._cv.wait(timeout=timeout)

    # Backward compatibility helper for existing synchronous check calls
    def check_scheduled(self, config: Dict[str, Any], current_time_str: str) -> bool:
        """Backward-compatible synchronous check."""
        return False

    def check_eye_break(self, config: Dict[str, Any], now_ts: float) -> bool:
        return False

    def check_hydration(self, config: Dict[str, Any], now_dt: datetime, now_ts: float) -> bool:
        return False

    def check_late_night(self, config: Dict[str, Any], now_dt: datetime, now_ts: float) -> bool:
        return False
