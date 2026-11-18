"""Unit tests for the PersonaEngine and personality system."""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from mac_assistant.personality import PersonaEngine, PersonaMoodState


class TestPersonality(unittest.TestCase):
    def setUp(self):
        self.engine = PersonaEngine()

    def test_personas_loaded(self):
        """Verifies jarvis, friday, and alfred personas load with complete pools."""
        for pid in ("jarvis", "friday", "alfred"):
            p = self.engine.get_persona(pid)
            self.assertEqual(p["id"], pid)
            self.assertIn("line_pools", p)
            pools = p["line_pools"]
            for expected_event in ("unlock_greeting", "wake_from_sleep", "morning_briefing_intro", "eye_break", "hydration", "tea", "lunch", "end_of_day", "late_night", "shutdown"):
                self.assertIn(expected_event, pools, f"Missing {expected_event} in {pid}")

    def test_no_immediate_repeats(self):
        """Ensures that across 50 successive picks, the picker never repeats immediately."""
        last_pick = None
        for _ in range(50):
            msg, _ = self.engine.pick("eye_break", context={"name": "Sir"}, config={"assistant_persona": "jarvis"})
            self.assertNotEqual(msg, last_pick)
            last_pick = msg

    def test_placeholder_resolution_safe_fallback(self):
        """Placeholders like {name}, {time}, {repo} must resolve cleanly even with empty context."""
        msg, _ = self.engine.pick("tea", context={}, config={"assistant_persona": "friday"})
        self.assertNotIn("{name}", msg)
        self.assertNotIn("{time}", msg)

    def test_quick_unlock_streak(self):
        """Quick unlocks under 2 minutes should choose short lines."""
        # 1st unlock
        is_quick, _ = self.engine.record_unlock()
        # 2nd immediate unlock
        is_quick, _ = self.engine.record_unlock()
        self.assertTrue(is_quick)

        msg, _ = self.engine.pick("unlock_greeting", context={"quick_unlock": True}, config={"assistant_persona": "friday"})
        self.assertLess(len(msg.split()), 10)  # Quick unlocks are short and snappy

    def test_late_night_escalation_cap(self):
        """Late-night nudges escalate through level 1, 2, 3 and cap at level 3."""
        l1 = self.engine.record_late_night_nudge()
        l2 = self.engine.record_late_night_nudge()
        l3 = self.engine.record_late_night_nudge()
        l4 = self.engine.record_late_night_nudge()

        self.assertEqual(l1, 1)
        self.assertEqual(l2, 2)
        self.assertEqual(l3, 3)
        self.assertEqual(l4, 3)  # Capped at 3

    def test_mood_rate_pitch_tuning(self):
        """Mood shifts adjust speech rate and prepend pitch commands."""
        # Calm mood
        self.engine._mood_state.current_mood = "calm"
        msg_calm, rate_calm = self.engine.pick("hydration", context={"name": "Sir"}, config={"assistant_persona": "jarvis"})

        # Stern mood
        self.engine._mood_state.current_mood = "stern"
        msg_stern, rate_stern = self.engine.pick("hydration", context={"name": "Sir"}, config={"assistant_persona": "jarvis"})

        self.assertLess(rate_stern, rate_calm)
        self.assertTrue(msg_stern.startswith("[[pbas"))

    def test_invalid_persona_fallback(self):
        """Invalid or non-existent persona IDs safely fall back without error."""
        p = self.engine.get_persona("non_existent_robot_999")
        self.assertIsNotNone(p)
        self.assertIn("voice", p)

    def test_adding_new_persona_no_code_change(self):
        """Adding a new JSON file to personas/ is automatically detected."""
        temp_dir = tempfile.mkdtemp()
        try:
            from mac_assistant import personality
            orig_dir = personality.PERSONAS_DIR
            personality.PERSONAS_DIR = Path(temp_dir)

            new_persona_file = Path(temp_dir) / "custom_butler.json"
            new_persona_file.write_text('{"id": "custom_butler", "name": "Custom", "voice": "Alex", "line_pools": {"lunch": ["Custom lunch call, {name}."]}}')

            engine = PersonaEngine()
            loaded = engine.get_persona("custom_butler")
            self.assertEqual(loaded["id"], "custom_butler")
            msg, _ = engine.pick("lunch", context={"name": "Sir"}, config={"assistant_persona": "custom_butler"})
            self.assertEqual(msg, "Custom lunch call, Sir.")

            personality.PERSONAS_DIR = orig_dir
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
