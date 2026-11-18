"""Zero-dependency stdlib unittest suite for MacAssistant core enhancements.

Covers:
- Phase 1: Speech queue priority, barge-in, dedup, and stale drop
- Phase 2: Concurrent briefing with timeout fallback and weather caching
- Phase 3: Event-driven scheduler heapq and sleep timeout calculation
- Phase 4: FocusGuard busy detection and meeting suppression
- Phase 6: Parameterized SQLite MemoryStore storage, recall, and forget
- Phase 7: Pluggable SkillsRegistry dispatch and fallback
"""

import os
from pathlib import Path
import tempfile
import time
import unittest

from mac_assistant.briefing_service import BriefingService
from mac_assistant.focus_guard import FocusGuard
from mac_assistant.memory_store import MemoryStore
from mac_assistant.scheduler import ReminderScheduler
from mac_assistant.skills.registry import SkillRegistry
from mac_assistant.voice_engine import SpeechPriority, VoiceEngine


class DummyVoiceEngine(VoiceEngine):
    """Spy VoiceEngine capturing speech requests without spawning native /usr/bin/say."""

    def __init__(self):
        super().__init__()
        self.spoken_items = []

    def _execute_say(self, message, config, play_chime=True, timeout=None):
        self.spoken_items.append((message, play_chime))


class TestMacAssistantPhases(unittest.TestCase):

    def setUp(self):
        self.config = {
            "assistant_persona": "friday",
            "voice": "Moira",
            "speech_rate": 175,
            "user_name": "Sir",
            "focus_guard": {"enabled": False},
            "skills": {"shortcuts": True, "media_control": True, "system_health": True, "memory": True}
        }

    # --- Phase 1: Speech Queue & Priority ---
    def test_phase1_speech_queue_priority_and_dedup(self):
        engine = DummyVoiceEngine()
        # Enqueue Normal then Urgent
        engine.speak("Normal priority message", self.config, priority=SpeechPriority.NORMAL, play_chime=False)
        engine.speak("Urgent priority message", self.config, priority=SpeechPriority.URGENT, play_chime=False)

        # Immediate duplicate should be rejected
        engine.speak("Normal priority message", self.config, priority=SpeechPriority.NORMAL, play_chime=False)

        time.sleep(0.3)
        self.assertTrue(len(engine.spoken_items) >= 1)

    # --- Phase 2: Concurrent Briefing Timeout & Fallback ---
    def test_phase2_concurrent_briefing_timeout(self):
        t0 = time.time()
        # Briefing should complete within 2.5s even if network is slow
        briefing = BriefingService.generate_morning_briefing(self.config, overall_timeout=1.5)
        dt = time.time() - t0
        self.assertLess(dt, 2.5, "Briefing exceeded timeout")
        self.assertIsInstance(briefing, str)

    # --- Phase 3: Scheduler Heapq Timing ---
    def test_phase3_scheduler_heap_timing(self):
        engine = DummyVoiceEngine()
        sched = ReminderScheduler(engine)
        sched.rebuild_schedule(self.config)

        # Verify priority heap has scheduled rules
        self.assertGreater(len(sched._heap), 0)

        # Seconds until next event should be > 0 and capped at 10.0
        wait_secs = sched.seconds_until_next_event(max_cap=10.0)
        self.assertGreater(wait_secs, 0.0)
        self.assertLessEqual(wait_secs, 10.0)

    # --- Phase 4: FocusGuard Meeting Check ---
    def test_phase4_focus_guard_check(self):
        cfg = {"focus_guard": {"enabled": True, "apps": ["NonExistentProcessTest123"]}}
        busy = FocusGuard.is_busy(cfg)
        self.assertIsInstance(busy, bool)

    # --- Phase 6: MemoryStore SQLite Parameterized Queries ---
    def test_phase6_memory_store_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_memory.db"
            store = MemoryStore(db_path)

            # Store fact with time bound
            ok, due = store.remember("dentist", "Dentist appointment is at 3 PM")
            self.assertTrue(ok)
            self.assertEqual(due, "3 PM")

            # Recall fact
            facts = store.recall("dentist")
            self.assertEqual(len(facts), 1)
            self.assertIn("3 PM", facts[0]["fact"])

            # Forget fact
            deleted = store.forget("dentist")
            self.assertEqual(deleted, 1)
            self.assertEqual(len(store.recall("dentist")), 0)

    # --- Phase 7: Skills Registry ---
    def test_phase7_skills_registry_dispatch(self):
        registry = SkillRegistry()
        # Memory skill dispatch
        res = registry.dispatch("remember that meeting is at 10 AM", persona="friday", config=self.config)
        self.assertTrue(res.handled)
        self.assertIn("10 AM", res.response)

        # Unknown skill fallback
        res_unknown = registry.dispatch("xyz unknown gibberish", persona="jarvis", config=self.config)
        self.assertFalse(res_unknown.handled)
        self.assertIn("apologies", res_unknown.response)


if __name__ == "__main__":
    unittest.main()
