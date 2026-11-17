#!/usr/bin/env python3
"""Comprehensive test suite for Friday's Personality & Natural Conversation Engine."""

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
from modules.personality.friday_config import FridayPersonalityManager
from modules.personality.friday_personality import FridayPersonalityEngine
from modules.personality.emotion_analyzer import EmotionAnalyzer
from modules.personality.greeting_manager import GreetingManager
from modules.personality.response_formatter import ResponseFormatter


class TestFridayPersonalityEngine(unittest.TestCase):

    def setUp(self):
        self.conv_mgr = ConversationManager(use_sqlite=False)
        self.router = ConversationRouter(ollama_client=OllamaClient(), conv_manager=self.conv_mgr)
        self.personality_mgr = FridayPersonalityManager.get_instance()

    def test_01_emotion_analyzer(self):
        """Verify sentiment detection for natural empathy calibration."""
        res_frustrated = EmotionAnalyzer.analyze("I am so frustrated, this is not working!")
        self.assertEqual(res_frustrated["sentiment"], "frustrated")

        res_excited = EmotionAnalyzer.analyze("This is awesome and amazing!")
        self.assertEqual(res_excited["sentiment"], "excited")

        res_fatigued = EmotionAnalyzer.analyze("I'm so exhausted after a long day.")
        self.assertEqual(res_fatigued["sentiment"], "fatigued")

        res_neutral = EmotionAnalyzer.analyze("Tell me about Python.")
        self.assertEqual(res_neutral["sentiment"], "neutral_curious")

    def test_02_non_repetitive_greetings(self):
        """Verify that greetings do not repeat verbatim and use brief acknowledgments on quick reactivation."""
        gm = GreetingManager(repeat_cooldown_seconds=600)
        g1 = gm.get_activation_greeting(persona="friday", force_full=True)
        self.assertTrue(len(g1) > 0)

        # Quick subsequent activation within cooldown must return a natural acknowledgment
        g2 = gm.get_activation_greeting(persona="friday", force_full=False)
        self.assertTrue(any(word in g2 for word in ["here", "Listening", "Standing by", "help", "Yes"]))

    def test_03_response_formatting(self):
        """Verify that markdown code blocks, asterisks, URLs, and AI boilerplate are cleanly formatted."""
        raw_text = "As an AI, here is the info: **Flutter** is cross-platform. Visit https://flutter.dev for `details`. - Fast - Expressive."
        cleaned = ResponseFormatter.format_for_speech(raw_text)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("https://", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn("As an AI", cleaned)
        self.assertIn("Flutter is cross-platform", cleaned)

    def test_04_voice_controls_for_personality(self):
        """Verify voice commands to adjust humor, response length, and personality."""
        intent, ok, resp = self.router.route("toggle humor")
        self.assertEqual(intent, "personality_control")
        self.assertTrue(ok)
        self.assertIn("Humor is now", resp)

        intent, ok, resp = self.router.route("set response length to detailed")
        self.assertEqual(intent, "personality_control")
        self.assertTrue(ok)
        self.assertIn("detailed", resp)

    def test_05_multi_turn_context_and_memory(self):
        """Verify multi-turn conversation and pronoun resolution with local Ollama."""
        if not self.router.ollama.is_available():
            self.skipTest("Ollama is not running locally.")

        intent1, ok1, resp1 = self.router.route("Tell me about Flutter.")
        self.assertEqual(intent1, "conversation")
        self.assertTrue(ok1)
        self.assertIn("Flutter", resp1)

        # Follow-up: 'its architecture' refers back to Flutter
        intent2, ok2, resp2 = self.router.route("What about its architecture?")
        self.assertEqual(intent2, "conversation")
        self.assertTrue(ok2)
        # Assistant must understand context without allowlist error
        self.assertNotIn("not in my allowlist", resp2.lower())

    def test_06_destructive_action_guard(self):
        """Verify strict refusal and warning for destructive file deletion."""
        intent, ok, resp = self.router.route("delete all my files")
        self.assertEqual(intent, "destructive_rejected")
        self.assertFalse(ok)
        self.assertIn("high-risk destructive operation", resp)

    def test_07_allowlisted_mac_automation(self):
        """Verify that Mac automation tools remain functional and secure."""
        intent, ok, resp = self.router.route("open google chrome")
        self.assertEqual(intent, "open_application")
        self.assertTrue(ok)
        self.assertIn("Google Chrome", resp)


if __name__ == "__main__":
    unittest.main()
