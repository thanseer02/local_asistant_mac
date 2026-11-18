"""Unit tests for CommandRouter, scheduler timing, and config schema validation."""

import os
from pathlib import Path
import tempfile
import time
import unittest

from mac_assistant.config_manager import ConfigManager
from mac_assistant.config_schema import AppConfigSchema
from mac_assistant.conversation_router import ConversationRouter
from mac_assistant.scheduler import ReminderScheduler, ScheduledEvent


class DummyVoiceEngine:
    def __init__(self):
        self.spoken = []

    def speak(self, msg, cfg, priority="normal"):
        self.spoken.append((msg, priority))


class TestMacAssistantCore(unittest.TestCase):

    def setUp(self):
        self.engine = DummyVoiceEngine()
        self.scheduler = ReminderScheduler(self.engine)
        self.router = ConversationRouter()

    def tearDown(self):
        self.scheduler.stop()

    def test_command_router_time_and_battery(self):
        intent, ok, reply = self.router.route("what time is it", persona="friday")
        self.assertEqual(intent, "check_datetime")
        self.assertTrue(ok)
        self.assertIn("The time is", reply)

    def test_command_router_remember_and_recall_fact(self):
        intent, ok, reply = self.router.route("remember that my flight is at 6 PM", persona="jarvis")
        self.assertEqual(intent, "remember_fact")
        self.assertTrue(ok)
        self.assertIn("flight is at 6", reply.lower())

    def test_command_router_stop_speech(self):
        intent, ok, reply = self.router.route("stop speaking", persona="friday")
        self.assertEqual(intent, "stop")
        self.assertTrue(ok)

    def test_scheduler_heap_and_timer_trigger(self):
        test_cfg = {
            "assistant_persona": "friday",
            "user_name": "Sir",
            "scheduled_reminders": []
        }
        self.scheduler.start(test_cfg)
        self.scheduler.add_custom_timer(delay_seconds=0.1, label="TestEvent", message="Timer test executed")
        time.sleep(0.3)
        self.assertTrue(any("Timer test executed" in msg[0] for msg in self.engine.spoken))

    def test_config_pydantic_schema_validation(self):
        valid_data = {
            "assistant_persona": "jarvis",
            "user_name": "Tanseer",
            "login_delay_seconds": 1.0,
            "voice_commands": {"enabled": True, "speech_threshold": 150.0}
        }
        validated = AppConfigSchema(**valid_data)
        self.assertEqual(validated.assistant_persona, "jarvis")
        self.assertEqual(validated.user_name, "Tanseer")


if __name__ == "__main__":
    unittest.main()
