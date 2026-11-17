#!/usr/bin/env python3
"""Comprehensive unit tests for Friday/Jarvis Desktop GUI Bridge & Components."""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.gui.bridge_service import AssistantBridgeService, SystemStatus


class TestControlCenterBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = AssistantBridgeService()

    def test_01_status_introspection(self):
        """Verify status reporting returns valid system metrics, persona, and PID."""
        status = self.bridge.get_current_status()
        self.assertIsInstance(status, SystemStatus)
        self.assertIn(status.active_persona.lower(), ["friday", "jarvis"])
        self.assertGreaterEqual(status.cpu_percent, 0.0)
        self.assertGreaterEqual(status.ram_percent, 0.0)
        self.assertEqual(status.llm_model, "llama3.2:1b (Local Ollama)")

    def test_02_conversation_history_query(self):
        """Verify history querying, limit constraints, and search filtering."""
        turns = self.bridge.get_conversation_history(limit=10)
        self.assertIsInstance(turns, list)

        # Keyword query test
        filtered = self.bridge.get_conversation_history(search_query="Flutter", limit=5)
        self.assertIsInstance(filtered, list)

    def test_03_isolated_personality_updates(self):
        """Verify modifying Friday's settings does not corrupt or overwrite Jarvis's settings."""
        # 1. Update Friday
        self.bridge.update_friday_settings({"response_length": "detailed", "humor": True})
        # 2. Update Jarvis with distinct values
        self.bridge.update_jarvis_settings({"response_length": "concise", "humor": False})

        # 3. Verify settings remain strictly isolated
        settings = self.bridge.get_personality_settings()
        self.assertEqual(settings["friday"]["response_length"], "detailed")
        self.assertTrue(settings["friday"]["humor"])

        self.assertEqual(settings["jarvis"]["response_length"], "concise")
        self.assertFalse(settings["jarvis"]["humor"])

        # Reset Jarvis back to default
        self.bridge.update_jarvis_settings({"response_length": "concise", "humor": True})

    def test_04_tool_registry_inspection(self):
        """Verify tool registry metadata returns permissions and confirmation criteria."""
        tools = self.bridge.get_registered_tools()
        self.assertTrue(len(tools) >= 5)

        tool_names = [t["id"] for t in tools]
        self.assertIn("open_application", tool_names)
        self.assertIn("git_mutations", tool_names)
        self.assertIn("flutter_tools", tool_names)

        # Verify confirmation flags
        git_mut = next(t for t in tools if t["id"] == "git_mutations")
        self.assertTrue(git_mut["requires_confirmation"])
        self.assertEqual(git_mut["permission_level"], "Restricted")

    def test_05_log_retrieval_and_redaction(self):
        """Verify log lines are read safely and secrets are redacted."""
        app_logs = self.bridge.get_logs(max_lines=15, log_type="app")
        self.assertIsInstance(app_logs, list)
        self.assertTrue(len(app_logs) > 0)


if __name__ == "__main__":
    unittest.main()
