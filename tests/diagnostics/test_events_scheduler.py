#!/usr/bin/env python3
"""Step 4 Diagnostic Script: Events and Scheduler fast-forward tests."""

from datetime import datetime
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.briefing_service import BriefingService
from mac_assistant.config_manager import ConfigManager
from mac_assistant.git_inspector import GitInspector
from mac_assistant.scheduler import ReminderScheduler


class TestVoiceSpy:
    def __init__(self):
        self.spoken = []

    def speak(self, msg, cfg, priority="normal"):
        self.spoken.append((msg, priority))


def run_event_scheduler_tests():
    print("=" * 70)
    print("DIAGNOSTIC STEP 4: Event & Scheduler Diagnostics")
    print("=" * 70)

    cfg = ConfigManager.load()

    # 1. Briefing & Git Inspector
    print("\n--- 1. Briefing & Git Inspector Diagnostic ---")
    t0 = time.time()
    data = BriefingService.get_briefing_data_concurrent(cfg, timeout=3.5)
    dt = (time.time() - t0) * 1000
    print(f"Concurrent Fetch completed in {dt:.1f}ms:")
    print(f"  Weather:     {data.get('weather')}")
    print(f"  Tasks Count: {len(data.get('tasks', []))}")
    print(f"  Git Summary: {data.get('git_summary')}")

    # 2. Scheduler Timing & Priority Heap Test
    print("\n--- 2. Scheduler Priority Queue Test ---")
    spy = TestVoiceSpy()
    sched = ReminderScheduler(spy)
    sched.start(cfg)

    # Fire quick timers
    sched.add_custom_timer(0.05, "TestTimer1", "First timer fired")
    sched.add_custom_timer(0.10, "TestTimer2", "Second timer fired")
    time.sleep(0.3)
    sched.stop()

    print(f"Spoken Alerts Count: {len(spy.spoken)}")
    for msg, prio in spy.spoken:
        print(f"  [{prio}] {msg}")

    print("=" * 70)


if __name__ == "__main__":
    run_event_scheduler_tests()
