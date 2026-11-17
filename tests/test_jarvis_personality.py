#!/usr/bin/env python3
"""Comprehensive test suite for Jarvis's Sophisticated Personality Engine & Friday Dual Personality Selection."""

import sys
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.conversation_router import ConversationRouter
from mac_assistant.ollama_client import OllamaClient
from modules.ai.conversation_manager import ConversationManager
from modules.personality.jarvis_config import JarvisPersonalityManager
from modules.personality.jarvis_personality import JarvisPersonalityEngine
from modules.personality.friday_config import FridayPersonalityManager
from modules.personality.friday_personality import FridayPersonalityEngine
from modules.personality.greeting_manager import GreetingManager
from modules.personality.response_formatter import ResponseFormatter


class TestJarvisAndDualPersonality(unittest.TestCase):

    def setUp(self):
        self.conv_mgr = ConversationManager(use_sqlite=False)
        self.router = ConversationRouter(ollama_client=OllamaClient(), conv_manager=self.conv_mgr)
        self.jarvis_mgr = JarvisPersonalityManager.get_instance()
        self.friday_mgr = FridayPersonalityManager.get_instance()

    def test_01_jarvis_system_prompt_structure(self):
        """Verify Jarvis system prompt contains required executive assistant directives and subtle British wit."""
        engine = JarvisPersonalityEngine()
        engine.mgr.config.humor = True
        prompt = engine.build_system_prompt("Jarvis, what is the status of our systems?")
        
        self.assertIn("You are JARVIS", prompt)
        self.assertIn("executive assistant", prompt)
        self.assertIn("composed, articulate, concise and precise", prompt)
        self.assertIn("subtle British-style wit", prompt)
        self.assertIn("Never sound robotic", prompt)
        self.assertIn("claim actions succeeded unless confirmed", prompt)
        self.assertIn("Respect tools and permissions", prompt)

    def test_02_jarvis_greetings_and_sir_usage(self):
        """Verify Jarvis uses respectful 'Sir' and distinct time-aware and cooldown greetings."""
        gm = GreetingManager(repeat_cooldown_seconds=600)
        
        # Fresh wake greeting
        j_fresh = gm.get_activation_greeting(persona="jarvis", force_full=True)
        self.assertIn("Sir", j_fresh)
        
        # Cooldown acknowledgment
        j_ack = gm.get_activation_greeting(persona="jarvis", force_full=False)
        self.assertIn("Sir", j_ack)

        # Friday greeting should NOT be forced to use Sir
        f_fresh = gm.get_activation_greeting(persona="friday", force_full=True)
        self.assertNotIn("Boss", f_fresh)

    def test_03_independent_settings(self):
        """Verify Jarvis and Friday settings are completely independent."""
        # Adjust Jarvis length
        self.jarvis_mgr.set_response_length("detailed")
        self.assertEqual(self.jarvis_mgr.config.response_length, "detailed")
        
        # Adjust Friday length
        self.friday_mgr.set_response_length("concise")
        self.assertEqual(self.friday_mgr.config.response_length, "concise")

        # Verify independence
        self.assertNotEqual(self.jarvis_mgr.config.response_length, self.friday_mgr.config.response_length)

        # Reset Jarvis
        self.jarvis_mgr.set_response_length("concise")

    def test_04_dual_persona_selection_by_wake_word(self):
        """Verify that conversation router correctly selects Friday or Jarvis engine."""
        # Friday wake call
        intent_f, ok_f, resp_f = self.router.route("hello", persona="friday")
        self.assertEqual(intent_f, "wake_call")
        self.assertTrue(ok_f)

        # Jarvis wake call
        intent_j, ok_j, resp_j = self.router.route("hello", persona="jarvis")
        self.assertEqual(intent_j, "wake_call")
        self.assertTrue(ok_j)
        self.assertIn("Sir", resp_j)

    def test_05_dynamic_personality_voice_commands(self):
        """Verify dynamic voice adjustments operate on active persona."""
        # Toggle humor for Jarvis
        intent, ok, resp = self.router.route("toggle humor", persona="jarvis")
        self.assertEqual(intent, "personality_control")
        self.assertTrue(ok)
        self.assertIn("Jarvis wit and humor", resp)

        # Toggle humor for Friday
        intent_f, ok_f, resp_f = self.router.route("toggle humor", persona="friday")
        self.assertEqual(intent_f, "personality_control")
        self.assertTrue(ok_f)
        self.assertIn("Humor is now", resp_f)

    def test_06_destructive_guard_for_both_personas(self):
        """Verify safety guard is enforced identically for Friday and Jarvis."""
        for p in ["friday", "jarvis"]:
            intent, ok, resp = self.router.route("rm -rf all files", persona=p)
            self.assertEqual(intent, "destructive_rejected")
            self.assertFalse(ok)
            self.assertIn("high-risk destructive operation", resp)

    def test_07_mac_automation_for_both_personas(self):
        """Verify Mac automation executes securely under both personas."""
        for p in ["friday", "jarvis"]:
            intent, ok, resp = self.router.route("check the time", persona=p)
            self.assertEqual(intent, "check_datetime")
            self.assertTrue(ok)
            self.assertIn("The time is", resp)


if __name__ == "__main__":
    unittest.main()
