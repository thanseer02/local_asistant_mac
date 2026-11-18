"""Unit tests for the exact, robust ReminderScheduler implementation."""

import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from mac_assistant.scheduler import (
    MAX_OVERDUE_SECONDS,
    ReminderScheduler,
    ScheduledRule,
    in_window,
    next_window_start,
)
from mac_assistant.voice_engine import SpeechPriority


class TestSchedulerStrict(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mock_voice = MagicMock()
        self.scheduler = ReminderScheduler(self.mock_voice)
        # Point state file to isolated temporary path
        self.scheduler._state_file = Path(self.temp_dir) / "scheduler_state.json"
        self.scheduler._state = {"last_fired_dates": {}, "last_fired_timestamps": {}}

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_in_window_midnight_crossing(self):
        """Tests 22:00 to 05:00 midnight-crossing window boundaries."""
        # Inside late-night window
        dt_2200 = datetime(2026, 11, 18, 22, 0)
        dt_2359 = datetime(2026, 11, 18, 23, 59)
        dt_0000 = datetime(2026, 11, 19, 0, 0)
        dt_0459 = datetime(2026, 11, 19, 4, 59)

        self.assertTrue(in_window(dt_2200, 22, 5))
        self.assertTrue(in_window(dt_2359, 22, 5))
        self.assertTrue(in_window(dt_0000, 22, 5))
        self.assertTrue(in_window(dt_0459, 22, 5))

        # Outside window
        dt_2159 = datetime(2026, 11, 18, 21, 59)
        dt_0500 = datetime(2026, 11, 19, 5, 0)
        dt_1200 = datetime(2026, 11, 19, 12, 0)

        self.assertFalse(in_window(dt_2159, 22, 5))
        self.assertFalse(in_window(dt_0500, 22, 5))
        self.assertFalse(in_window(dt_1200, 22, 5))

    def test_next_window_start(self):
        """Ensures next_window_start accurately targets next 22:00."""
        dt_morning = datetime(2026, 11, 18, 10, 30)
        target = next_window_start(dt_morning, 22)
        self.assertEqual(target.hour, 22)
        self.assertEqual(target.day, 18)

        dt_late = datetime(2026, 11, 18, 23, 0)
        target_next_day = next_window_start(dt_late, 22)
        self.assertEqual(target_next_day.hour, 22)
        self.assertEqual(target_next_day.day, 19)

    def test_state_persistence_atomic(self):
        """Verifies state is atomically saved and loaded across restarts."""
        self.scheduler._record_fired("daily_11:00", time.time())
        self.assertTrue(self.scheduler._state_file.exists())

        # Load fresh scheduler instance
        new_sched = ReminderScheduler(self.mock_voice)
        new_sched._state_file = self.scheduler._state_file
        new_sched._state = new_sched._load_state()

        self.assertTrue(new_sched.was_fired_today("daily_11:00"))
        self.assertFalse(new_sched.was_fired_today("daily_13:00"))

    def test_exactly_once_daily_reminder(self):
        """Daily alert should not fire if already recorded as fired today."""
        config = {
            "assistant_persona": "friday",
            "scheduled_reminders": [
                {"time": "11:00", "message": "Time for tea, {name}."}
            ]
        }
        # Mark 11:00 as already fired today
        self.scheduler._record_fired("daily_11:00")
        self.scheduler.rebuild_schedule(config)

        # Find daily_11:00 on the heap
        daily_rule = next(r for r in self.scheduler._heap if r.rule_id == "daily_11:00")
        self.assertGreater(daily_rule.due_epoch, time.time() + 3600.0)

        # Even if artificially due, process_due_events must skip it
        daily_rule.due_epoch = time.time() - 10.0
        # Re-heapify so it's at the top
        import heapq
        heapq.heapify(self.scheduler._heap)
        spoken = self.scheduler.process_due_events(config)
        self.assertFalse(spoken)
        self.mock_voice.speak.assert_not_called()

    def test_missed_event_policy_within_two_minutes(self):
        """Overdue <= 120s must fire, overdue > 120s must be dropped."""
        handler_called = []
        rule_valid = ScheduledRule(
            due_epoch=time.time() - 60.0,  # 1 min overdue (<= 120s)
            rule_id="test_valid",
            handler=lambda cfg: handler_called.append("valid")
        )
        rule_stale = ScheduledRule(
            due_epoch=time.time() - 300.0,  # 5 min overdue (> 120s)
            rule_id="test_stale",
            handler=lambda cfg: handler_called.append("stale")
        )

        import heapq
        self.scheduler._heap = [rule_stale, rule_valid]
        heapq.heapify(self.scheduler._heap)

        self.scheduler.process_due_events({})
        self.assertIn("valid", handler_called)
        self.assertNotIn("stale", handler_called)

    def test_wake_from_sleep_single_reminder_cap(self):
        """On system wake, at most ONE reminder should fire, never a burst."""
        fired = []
        rule1 = ScheduledRule(
            due_epoch=time.time() - 30.0,
            rule_id="eye_break",
            handler=lambda cfg: fired.append("eye_break")
        )
        rule2 = ScheduledRule(
            due_epoch=time.time() - 40.0,
            rule_id="daily_11:00",
            handler=lambda cfg: fired.append("daily_11:00")
        )
        rule3 = ScheduledRule(
            due_epoch=time.time() - 20.0,
            rule_id="hydration",
            handler=lambda cfg: fired.append("hydration")
        )

        import heapq
        self.scheduler._heap = [rule1, rule2, rule3]
        heapq.heapify(self.scheduler._heap)

        # Trigger wake
        self.scheduler.on_system_wake({})

        # Exactly ONE reminder must have fired (daily alert preferred over intervals)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0], "daily_11:00")

    def test_hydration_workday_rollover(self):
        """Hydration should roll over from Friday night to Monday morning 9:00."""
        friday_evening = datetime(2026, 11, 20, 19, 0)  # Friday 19:00
        hydro_cfg = {"start_hour": 9, "end_hour": 18}

        next_due_dt = datetime.fromtimestamp(
            self.scheduler._compute_next_hydration_epoch(friday_evening, hydro_cfg)
        )
        self.assertEqual(next_due_dt.weekday(), 0)  # Monday
        self.assertEqual(next_due_dt.hour, 9)
        self.assertEqual(next_due_dt.day, 23)


if __name__ == "__main__":
    unittest.main()
