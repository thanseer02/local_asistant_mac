"""Unit tests for multi-boot random persona selection, session consistency, and weights."""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from mac_assistant.personality import PersonaEngine


class TestPersonaSelection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = PersonaEngine()
        self.engine._state_file = Path(self.temp_dir) / "persona_state.json"
        self.config = {
            "persona_mode": "random",
            "persona_history_size": 3,
            "persona_pool": [],
            "persona_weights": {},
            "user_name": "Sir"
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_500_simulated_boots_history_window(self):
        """Simulates 500 consecutive boots and verifies no repeat within history window of 3."""
        state = {
            "current_persona": "",
            "history": [],
            "last_boot_sec": 1000,
            "last_session_id": "sess_0",
            "last_used_timestamps": {}
        }
        self.engine._save_persona_state(state)

        history_window = 3
        for i in range(1, 501):
            chosen = self.engine.select_persona_for_session(self.config, state)
            recent_3 = state.get("history", [])[-history_window:]
            self.assertNotIn(chosen, recent_3, f"Boot {i}: {chosen} was repeated in recent {recent_3}")

            hist = state.get("history", [])
            hist.append(chosen)
            state["history"] = hist[-history_window:]
            state["current_persona"] = chosen
            state["last_boot_sec"] = 1000 + i
            state.setdefault("last_used_timestamps", {})[chosen] = time.time()
            self.engine._save_persona_state(state)

    def test_fixed_and_rotate_modes(self):
        """Tests that fixed mode stays fixed and rotate mode cycles sequentially."""
        cfg_fixed = {"persona_mode": "fixed", "persona": "jarvis"}
        state = {"current_persona": "friday", "history": []}
        chosen = self.engine.select_persona_for_session(cfg_fixed, state)
        self.assertEqual(chosen, "jarvis")

        cfg_rotate = {
            "persona_mode": "rotate",
            "persona_pool": ["alfred", "coach", "friday", "jarvis"]
        }
        state_rot = {"current_persona": "coach"}
        p1 = self.engine.select_persona_for_session(cfg_rotate, state_rot)
        self.assertEqual(p1, "friday")

        state_rot["current_persona"] = "friday"
        p2 = self.engine.select_persona_for_session(cfg_rotate, state_rot)
        self.assertEqual(p2, "jarvis")

    def test_daemon_crash_preserves_persona(self):
        """A daemon restart with the same boot epoch and session id must preserve the active persona."""
        state = {
            "current_persona": "noir",
            "history": ["noir"],
            "last_boot_sec": 1794971694,
            "last_session_id": "test_sess_1"
        }
        self.engine._save_persona_state(state)

        # Mock current boot and session to match stored state
        import mac_assistant.personality as p_mod
        orig_boot = p_mod.get_system_boot_epoch
        orig_sess = p_mod.get_current_session_id
        try:
            p_mod.get_system_boot_epoch = lambda: 1794971694
            p_mod.get_current_session_id = lambda: "test_sess_1"

            # Fresh engine instance loading the same state
            test_engine = PersonaEngine()
            test_engine._state_file = self.engine._state_file
            pid = test_engine.initialize_session(self.config, force_reroll=False)
            self.assertEqual(pid, "noir")
            self.assertFalse(test_engine._is_new_session)

            # Now simulate a new reboot (new boot epoch)
            p_mod.get_system_boot_epoch = lambda: 1794980000
            pid_reboot = test_engine.initialize_session(self.config, force_reroll=False)
            self.assertNotEqual(pid_reboot, "noir")
            self.assertTrue(test_engine._is_new_session)
        finally:
            p_mod.get_system_boot_epoch = orig_boot
            p_mod.get_current_session_id = orig_sess

    def test_corrupt_state_recovery(self):
        """A corrupt persona_state.json should be cleanly caught and recovered."""
        self.engine._state_file.write_text("{ corrupt json syntax !!! ")
        state = self.engine._load_persona_state()
        self.assertIn("history", state)
        self.assertIn("current_persona", state)

    def test_missing_voice_exclusion(self):
        """Personas whose macOS voices are not installed are excluded from selection."""
        import mac_assistant.personality as p_mod
        orig_voices = p_mod.get_installed_voices
        try:
            # Emulate only Daniel and Moira installed
            p_mod.get_installed_voices = lambda: {"daniel", "moira"}

            state = {"current_persona": "", "history": []}
            cfg = {"persona_mode": "random", "persona_history_size": 1}

            for _ in range(20):
                chosen = self.engine.select_persona_for_session(cfg, state)
                self.assertIn(chosen, ("jarvis", "friday", "alfred"))
        finally:
            p_mod.get_installed_voices = orig_voices


if __name__ == "__main__":
    unittest.main()
