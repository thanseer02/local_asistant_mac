#!/usr/bin/env python3
"""Comprehensive security and functional unit tests for Developer Assistant Module."""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.conversation_router import ConversationRouter
from mac_assistant.ollama_client import OllamaClient
from modules.ai.conversation_manager import ConversationManager
from modules.developer import (
    DeveloperSecurityPolicy, ProjectManager, GitManager,
    FlutterManager, PythonManager, LogInspector, ErrorAnalyzer
)


class TestDeveloperAssistant(unittest.TestCase):

    def setUp(self):
        self.conv_mgr = ConversationManager(use_sqlite=False)
        self.router = ConversationRouter(ollama_client=OllamaClient(), conv_manager=self.conv_mgr)
        self.ws_root = Path(__file__).resolve().parent.parent

    # ------------------ Security Policy Tests ------------------

    def test_01_security_path_validation(self):
        """Verify that paths outside approved developer directories are blocked."""
        # Forbidden system path
        forbidden_path = Path("/etc/passwd")
        valid, safe_p, reason = DeveloperSecurityPolicy.validate_project_path(forbidden_path)
        self.assertFalse(valid)
        self.assertIn("outside approved", reason)

        # Nonexistent path
        valid, safe_p, reason = DeveloperSecurityPolicy.validate_project_path("/Users/tanseer/NonExistentFolder123")
        self.assertFalse(valid)
        self.assertIn("does not exist", reason)

        # Approved workspace path
        valid, safe_p, reason = DeveloperSecurityPolicy.validate_project_path(self.ws_root)
        self.assertTrue(valid)
        self.assertEqual(safe_p, self.ws_root)

    def test_02_secret_redaction(self):
        """Verify credentials, tokens, and API keys are redacted from outputs."""
        sample_with_secret = (
            "Connecting with api_key='sk_test_51AbcDef1234567890' and "
            "token: ghp_1234567890abcdef1234567890abcdef1234"
        )
        clean = DeveloperSecurityPolicy.redact_secrets(sample_with_secret)
        self.assertNotIn("sk_test_51AbcDef1234567890", clean)
        self.assertNotIn("ghp_1234567890", clean)
        self.assertIn("[REDACTED_SECRET]", clean)

    def test_03_confirmation_requirement_for_mutations(self):
        """Verify that Git commits, pushes, and build commands require explicit confirmation."""
        # Unconfirmed commit attempt
        res = GitManager.commit(self.ws_root, "Test commit without confirmation", confirmed=False)
        self.assertFalse(res.success)
        self.assertTrue(res.requires_confirmation)
        self.assertIn("Confirmation required", res.stderr)

        # Unconfirmed Flutter pub get
        res_f = FlutterManager.pub_get(self.ws_root, confirmed=False)
        self.assertFalse(res_f.success)
        self.assertTrue(res_f.requires_confirmation)

    # ------------------ Functional Tests ------------------

    def test_04_project_manager_detection(self):
        """Verify project recognition and type identification."""
        ptype = ProjectManager.inspect_project_type(self.ws_root)
        self.assertIn(ptype, ["python", "git"])

        projects = ProjectManager.list_projects(limit=5)
        self.assertTrue(len(projects) > 0)
        self.assertTrue(any(p["name"] == self.ws_root.name for p in projects))

    def test_05_git_manager_read_only(self):
        """Verify Git read-only commands (status, branch, log, diff, remote) execute without confirmation."""
        # Status
        status_res = GitManager.get_status(self.ws_root)
        self.assertTrue(status_res.success)
        self.assertFalse(status_res.requires_confirmation)

        # Branch
        branch_res = GitManager.get_active_branch(self.ws_root)
        self.assertTrue(branch_res.success)
        self.assertTrue(len(branch_res.stdout.strip()) > 0)

        # Log
        log_res = GitManager.get_log(self.ws_root, max_count=2)
        self.assertTrue(log_res.success)

    def test_06_python_venv_detection(self):
        """Verify virtual environment detection and python binary resolution."""
        venv_dir, py_bin = PythonManager.detect_venv(self.ws_root)
        self.assertIsNotNone(py_bin)
        self.assertTrue(py_bin.exists())

    def test_07_log_inspector(self):
        """Verify log inspection and summary formatting."""
        log_path = Path("/tmp/macassistant-error.log")
        data = LogInspector.inspect_file(log_path, max_lines=20)
        self.assertTrue(data.get("exists"))
        self.assertIn("errors", data)

        speech = LogInspector.get_summary_speech(log_path)
        self.assertTrue(len(speech) > 0)

    # ------------------ Voice Command Routing Tests ------------------

    def test_08_voice_git_status_friday_and_jarvis(self):
        """Verify natural voice commands for Git status through Friday and Jarvis."""
        # Friday routing
        intent_f, ok_f, resp_f = self.router.route("check git status", persona="friday")
        self.assertEqual(intent_f, "dev_git_status")
        self.assertTrue(ok_f)
        self.assertIn(self.ws_root.name, resp_f)

        # Jarvis routing
        intent_j, ok_j, resp_j = self.router.route("git status", persona="jarvis")
        self.assertEqual(intent_j, "dev_git_status")
        self.assertTrue(ok_j)
        self.assertIn("branch", resp_j)

    def test_09_voice_confirmation_flow(self):
        """Verify interactive two-step confirmation flow for mutating developer commands."""
        # Step 1: User requests commit -> Assistant prompts for confirmation
        intent1, ok1, resp1 = self.router.route("git commit changes with message added developer module", persona="jarvis")
        self.assertEqual(intent1, "dev_confirmation_required")
        self.assertTrue(ok1)
        self.assertIn("Sir, please confirm", resp1)
        self.assertIsNotNone(self.router._pending_confirmation)

        # Step 2A: User declines
        intent_dec, ok_dec, resp_dec = self.router.route("no cancel", persona="jarvis")
        self.assertEqual(intent_dec, "action_cancelled")
        self.assertIn("aborted", resp_dec)
        self.assertIsNone(self.router._pending_confirmation)


if __name__ == "__main__":
    unittest.main()
