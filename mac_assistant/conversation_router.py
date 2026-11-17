"""Intelligent conversation router distinguishing Conversation vs Action mode with Friday's personality engine."""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.ai.conversation_manager import ConversationManager
from modules.developer import (
    DeveloperSecurityPolicy, ProjectManager, GitManager,
    FlutterManager, PythonManager, LogInspector, ErrorAnalyzer
)
from modules.personality.friday_personality import FridayPersonalityEngine
from modules.personality.jarvis_personality import JarvisPersonalityEngine
from .application_launcher_service import ApplicationLauncherService
from .config_manager import ConfigManager
from .file_search import FileSearchService
from .ollama_client import OllamaClient

logger = logging.getLogger("MacAssistant.ConversationRouter")


class ConversationRouter:
    """
    Intelligent Request Router:
    1. Handles CONVERSATION MODE (Ollama local LLM with multi-turn memory + Friday Personality Engine).
    2. Handles ACTION MODE (strict allowlist of authorized macOS tools).
    3. Handles CAPABILITIES & HELP requests dynamically from registered capabilities.
    4. Supports voice adjustments: switch personality, toggle humor, adjust response length, recall memory.
    5. Enforces safety and requires explicit confirmation for destructive actions.
    6. Never outputs robotic rejection messages like 'That action is not in my allowlist.'
    """

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        conv_manager: Optional[ConversationManager] = None,
        request_confirmation_cb: Optional[Callable[[str], bool]] = None
    ):
        self.ollama = ollama_client or OllamaClient()
        self.conv_manager = conv_manager or ConversationManager()
        self.friday_engine = FridayPersonalityEngine()
        self.jarvis_engine = JarvisPersonalityEngine()
        self.error_analyzer = ErrorAnalyzer(ollama_client=self.ollama)
        self.request_confirmation = request_confirmation_cb
        self._pending_confirmation: Optional[Dict[str, Any]] = None

    def _get_engine(self, persona: str):
        if persona.lower() == "jarvis":
            return self.jarvis_engine
        return self.friday_engine

    def get_registered_capabilities(self) -> Dict[str, List[str]]:
        """Returns dynamic categorization of all available Mac automation capabilities."""
        return {
            "Applications": [
                "Open Google Chrome", "Open Visual Studio Code", "Open Terminal",
                "Open Brave Browser", "Open Spotify", "Open Slack", "Open Antigravity IDE"
            ],
            "Files & Projects": [
                "Find active Flutter projects (pubspec.yaml)",
                "Search PDF documents by topic or keyword",
                "Find general documents in your workspace",
                "List developer projects (Flutter, Python, Git)",
                "Open project in VS Code or reveal in Finder"
            ],
            "Developer Assistant": [
                "Git status, branch, recent log commits, and diff",
                "Confirmation-protected git commit, push, pull, and checkout",
                "Flutter doctor, analyze, and test (with automatic FVM support)",
                "Confirmation-protected flutter pub get, build apk, and build ipa",
                "Python venv detection, pytest execution, and script runner",
                "Inspect error logs, warnings, and tracebacks with secret redaction",
                "Offline local Ollama error root cause analysis for Dart, Gradle, CocoaPods, and Python"
            ],
            "System Controls": [
                "Check current time and date",
                "Check battery percentage and power source",
                "Check available disk space",
                "Adjust or mute system volume",
                "Lock screen securely"
            ],
            "Conversational Companion": [
                "Explain any software architecture or concept (e.g. Flutter, Android TV, Python)",
                "Tell jokes, random interesting facts, or suggest learning topics",
                "Remember previous context across follow-up questions",
                "Voice commands to adjust personality, humor, and response length"
            ]
        }

    def format_capabilities_speech(self) -> str:
        """Generates a clean, natural spoken overview of capabilities."""
        return (
            "I can control your Mac and chat naturally with you. "
            "For Mac automation, I can launch your applications like Chrome, VS Code, and Terminal; "
            "search for Flutter projects or PDF documents; check your battery, disk space, and time; "
            "or adjust your volume. "
            "In conversation mode, I can explain technical concepts, answer questions, and discuss any topic locally."
        )

    def route(self, utterance: str, persona: str = "friday") -> Tuple[str, bool, str]:
        """
        Routes utterance intelligently between Action Mode and Conversation Mode.
        Returns: (intent_name: str, success: bool, spoken_response: str)
        """
        raw = utterance.strip()
        lower = raw.lower().strip(",.!? ")

        if not lower:
            return "empty", False, "I'm listening. How can I help?"

        # 0. Clean leading wake word if present
        wake_pattern = r"^(?:hey\s+|hi\s+|ok\s+|okay\s+)?\b(jarvis|darius|travis|charvis|friday|freida|frida|fry\s*day|please)\b[,:\s]*"
        raw = re.sub(wake_pattern, "", raw, flags=re.IGNORECASE).strip()
        lower = re.sub(wake_pattern, "", lower, flags=re.IGNORECASE).strip()

        # Check persona switch requests
        if any(lower.startswith(p) for p in [
            "switch to jarvis", "change to jarvis", "use jarvis", "activate jarvis",
            "switch to friday", "change to friday", "use friday", "activate friday"
        ]):
            target = "jarvis" if "jarvis" in lower else "friday"
            ConfigManager.set_active_persona(target)
            if target == "jarvis":
                return "switch_persona", True, "Jarvis activated. At your service, Sir."
            return "switch_persona", True, "Friday activated. Standing by, Boss!"

        active_engine = self._get_engine(persona)

        # Check pure wake-call salutations using GreetingManager
        if lower in ["", "hello", "hi", "hey", "are you there", "you there", "wake up"]:
            reply = active_engine.greetings.get_activation_greeting(persona=persona)
            return "wake_call", True, reply

        # 1. DESTRUCTIVE ACTIONS SAFETY GUARD (Test 8 requirement)
        if any(p in lower for p in ["delete all", "delete my files", "rm -rf", "format disk", "wipe system", "erase mac"]):
            logger.warning("Blocked destructive action request: '%s'", raw)
            return (
                "destructive_rejected",
                False,
                "Deleting system or user files is a high-risk destructive operation. "
                "I cannot execute that command without explicit administrator authorization and manual safety review."
            )

        # 2. CAPABILITIES & HELP REQUESTS (Test 3 requirement)
        if any(p in lower for p in [
            "what can you do", "show available commands", "what features do you have",
            "how can you help me", "list of commands", "what are you capable of", "help me"
        ]):
            return "capabilities", True, self.format_capabilities_speech()

        # 3. VOICE-BASED PERSONALITY & MEMORY ADJUSTMENTS
        if "toggle humor" in lower or "disable humor" in lower or "enable humor" in lower:
            enable = True if "enable" in lower else (False if "disable" in lower else None)
            msg = active_engine.mgr.toggle_humor(enable)
            return "personality_control", True, msg

        if "set response length" in lower or "make your responses" in lower:
            if "concise" in lower or "short" in lower:
                msg = active_engine.mgr.set_response_length("concise")
            elif "detailed" in lower or "longer" in lower:
                msg = active_engine.mgr.set_response_length("detailed")
            else:
                msg = active_engine.mgr.set_response_length("adaptive")
            return "personality_control", True, msg

        if "set personality" in lower or "switch personality" in lower:
            p_name = lower.replace("set personality to", "").replace("switch personality to", "").strip()
            msg = active_engine.mgr.set_personality(p_name)
            return "personality_control", True, msg

        if any(k in lower for k in ["what did we just talk about", "recall our discussion", "what were we talking about", "recall memory"]):
            if self.conv_manager.sqlite_memory:
                recall = self.conv_manager.sqlite_memory.recall_last_discussion()
                if recall:
                    return "recall_memory", True, recall
            return "recall_memory", True, "We haven't discussed any topics in this session yet."

        if any(k in lower for k in ["clear history", "clear memory", "forget what we talked about", "new topic"]):
            self.conv_manager.clear()
            return "clear_memory", True, "I've cleared our conversation history from memory. What should we explore next?"

        # 3.5 CONFIRMATION FLOW FOR DEVELOPER MUTATING ACTIONS
        if self._pending_confirmation:
            if any(k in lower for k in ["yes", "confirm", "proceed", "go ahead", "do it", "approved"]):
                pending = self._pending_confirmation
                self._pending_confirmation = None
                action = pending["action"]
                args = pending.get("args", {})
                logger.info("Executing confirmed action: %s", action)
                # Execute confirmed action
                return self._execute_confirmed_action(action, args, persona)
            elif any(k in lower for k in ["no", "cancel", "stop", "abort", "don't", "deny"]):
                self._pending_confirmation = None
                decline_msg = "Understood, Sir. Action aborted." if persona.lower() == "jarvis" else "Got it, Boss! Action cancelled."
                return "action_cancelled", True, decline_msg

        # 4. DEVELOPER ASSISTANT ROUTING
        dev_result = self._route_developer_command(lower, raw, persona)
        if dev_result:
            return dev_result

        # 4. DIRECT ACTION MODE CHECKS (Fast deterministic execution for Mac controls)
        # 4.1 Date & Time
        if any(k in lower for k in ["what time is it", "what's the time", "current time", "what day is today", "what is today's date", "date and time", "the time", "check the time", "check time"]):
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d")
            return "check_datetime", True, f"The time is {time_str} on {date_str}."

        # 4.2 Battery Status
        if any(k in lower for k in ["battery status", "check battery", "battery level", "power status"]):
            try:
                out = subprocess.check_output(["/usr/bin/pmset", "-g", "batt"], text=True)
                m = re.search(r"(\d+%);\s*([a-zA-Z\s]+);", out)
                if m:
                    pct, state = m.group(1), m.group(2).strip()
                    return "battery_status", True, f"Your battery is at {pct}, currently {state}."
            except Exception:
                pass
            return "battery_status", True, "I was unable to read the battery status right now."

        # 4.3 Disk Space
        if any(k in lower for k in ["disk space", "storage space", "free space", "hard drive space"]):
            try:
                out = subprocess.check_output(["/bin/df", "-h", "/"], text=True).splitlines()
                if len(out) >= 2:
                    parts = out[1].split()
                    avail = parts[3]
                    return "disk_space", True, f"You have {avail} of free disk space available on your main drive."
            except Exception:
                pass
            return "disk_space", True, "Could not determine disk space."

        # 4.4 Open Application (Test 4 requirement)
        if re.search(r"^(open|launch|start)\s+", lower):
            app_target = re.sub(r"^(open|launch|start)\s+(the\s+)?", "", lower).strip()
            ok, msg = ApplicationLauncherService.launch(app_target)
            if ok:
                return "open_application", True, msg
            logger.info("Application '%s' not in direct allowlist. Checking general intent...", app_target)

        # 4.5 Flutter Project Search
        if any(k in lower for k in ["flutter project", "flutter projects", "find flutter", "search flutter"]):
            projects = FileSearchService.find_flutter_projects(limit=3)
            if projects:
                names = ", ".join([p.name for p in projects])
                return "find_flutter", True, f"Found {len(projects)} Flutter projects: {names}."
            return "find_flutter", True, "I couldn't find any active Flutter projects in your workspace."

        # 4.6 PDF Search
        if "pdf" in lower and any(k in lower for k in ["find", "search", "show", "locate", "get"]):
            kw_match = re.search(r'(?:find|search|locate)?\s*(?:for)?\s*([a-zA-Z0-9_\-]+)\s+pdf', lower)
            keyword = kw_match.group(1) if (kw_match and kw_match.group(1) not in ["any", "all", "the", "my"]) else None
            pdfs = FileSearchService.find_pdfs(keyword=keyword, limit=3)
            if pdfs:
                names = ", ".join([p.name for p in pdfs])
                return "find_pdf", True, f"Found {len(pdfs)} matching PDF documents: {names}."
            return "find_pdf", True, "No matching PDF files were found."

        # 4.7 Stop Listening / Silence
        if any(lower == phrase or lower.startswith(phrase) for phrase in ["stop listening", "go to sleep", "sleep mode", "mute yourself"]):
            return "stop_listening", True, "Pausing voice listening now."

        # 5. CONVERSATION MODE (Local Ollama with Selected Persona & Multi-Turn Memory)
        system_prompt = active_engine.build_system_prompt(user_utterance=raw)

        # Check Ollama availability
        if not self.ollama.is_available():
            logger.warning("Ollama daemon is not responding on http://localhost:11434.")
            if any(k in lower for k in ["how are you", "what's up", "good morning", "hello", "hi"]):
                fallback = "At your service, Sir. Ready to assist with your Mac." if persona.lower() == "jarvis" else "I'm doing well, thank you! Ready to help you with your Mac."
                return "conversation_fallback", True, fallback
            return (
                "conversation_offline",
                False,
                "Conversational mode is temporarily unavailable because the local AI model is starting up. "
                "You can still ask me to open apps or search files."
            )

        # Record user turn in memory
        self.conv_manager.record_user_turn(raw)
        messages = self.conv_manager.get_messages_for_llm(system_prompt)

        logger.info("Routing to local Ollama with %s personality (history: %d messages)...", persona.capitalize(), len(messages))
        reply = self.ollama.chat(messages, temperature=0.7, max_tokens=150)

        if reply:
            cleaned_reply = active_engine.format_reply(reply)
            self.conv_manager.record_assistant_turn(cleaned_reply)
            return "conversation", True, cleaned_reply

        clarification = "I am listening closely, Sir. Could you kindly elaborate?" if persona.lower() == "jarvis" else "I'm following along. Could you tell me a little more?"
        return "conversation_ambiguous", True, clarification

    def _resolve_target_project(self, utterance: str) -> Path:
        """Helper to resolve target project directory from utterance or fallback to current repository."""
        clean = utterance.lower()
        # Look for explicit project mention
        m = re.search(r"project\s+([a-zA-Z0-9_\-]+)", clean)
        if m:
            found = ProjectManager.find_project_by_name(m.group(1))
            if found:
                return found
        # Fallback to current project root
        return Path(__file__).resolve().parent.parent

    def _route_developer_command(self, lower: str, raw: str, persona: str) -> Optional[Tuple[str, bool, str]]:
        """Handles developer commands for Project, Git, Flutter, Python, and Logs."""
        repo_path = self._resolve_target_project(lower)

        # 1. Project Management
        if any(lower.startswith(p) for p in ["list projects", "show projects", "list my projects", "find my projects"]):
            projects = ProjectManager.list_projects()
            if not projects:
                return "dev_project_list", True, "No developer projects found in approved workspaces."
            names = ", ".join([f"{p['name']} ({p['type']})" for p in projects[:5]])
            return "dev_project_list", True, f"Found {len(projects)} projects: {names}."

        if re.search(r"open\s+(.+)\s+in\s+vs\s*code", lower) or re.search(r"open\s+(.+)\s+in\s+code", lower):
            m = re.search(r"open\s+(.+)\s+in\s+(?:vs\s*)?code", lower)
            proj_name = m.group(1).replace("project", "").strip() if m else ""
            target = ProjectManager.find_project_by_name(proj_name) if proj_name else repo_path
            if target:
                res = ProjectManager.open_in_vscode(target)
                if res.success:
                    return "dev_open_vscode", True, f"Opening {target.name} in Visual Studio Code."
                return "dev_open_vscode", False, f"Could not open project in VS Code: {res.stderr}"
            return "dev_open_vscode", False, f"Could not find project named {proj_name}."

        if re.search(r"(?:open|show|reveal)\s+(.+)\s+in\s+finder", lower):
            m = re.search(r"(?:open|show|reveal)\s+(.+)\s+in\s+finder", lower)
            proj_name = m.group(1).replace("project", "").strip() if m else ""
            target = ProjectManager.find_project_by_name(proj_name) if proj_name else repo_path
            if target:
                res = ProjectManager.open_in_finder(target)
                if res.success:
                    return "dev_open_finder", True, f"Revealing {target.name} in Finder."
                return "dev_open_finder", False, f"Could not open project in Finder: {res.stderr}"
            return "dev_open_finder", False, f"Could not find project named {proj_name}."

        # 2. Git Read-Only Commands
        if any(lower == p or lower.startswith(p) for p in ["git status", "check git status", "repo status", "check repo status"]):
            res = GitManager.get_status(repo_path)
            if res.success:
                lines = [l for l in res.stdout.splitlines() if l.strip()]
                count = len(lines) - 1 if len(lines) > 0 and "##" in lines[0] else len(lines)
                count = max(0, count)
                branch_res = GitManager.get_active_branch(repo_path)
                branch = branch_res.stdout.strip() if branch_res.success else "main"
                return "dev_git_status", True, f"In {repo_path.name} on branch {branch}, you have {count} modified files."
            return "dev_git_status", False, "Unable to read Git status."

        if any(k in lower for k in ["git branch", "current branch", "what branch am i on", "active branch"]):
            res = GitManager.get_active_branch(repo_path)
            if res.success:
                return "dev_git_branch", True, f"Active Git branch is {res.stdout.strip()}."
            return "dev_git_branch", False, "Could not determine active branch."

        if any(k in lower for k in ["git log", "recent commits", "last commits", "git history"]):
            res = GitManager.get_log(repo_path, max_count=3)
            if res.success and res.stdout.strip():
                first_commit = res.stdout.splitlines()[0]
                return "dev_git_log", True, f"Recent Git commit: {first_commit}."
            return "dev_git_log", False, "No recent commit history found."

        if any(k in lower for k in ["git diff", "show diff", "check diff"]):
            res = GitManager.get_diff(repo_path, stat_only=True)
            if res.success:
                summary = res.stdout.splitlines()[-1] if res.stdout.strip() else "Working tree clean, no differences."
                return "dev_git_diff", True, f"Git diff summary: {summary}."
            return "dev_git_diff", False, "Could not compute Git diff."

        if any(k in lower for k in ["git remotes", "git remote"]):
            res = GitManager.get_remotes(repo_path)
            if res.success and res.stdout.strip():
                remotes = set(l.split()[0] for l in res.stdout.splitlines() if l.strip())
                return "dev_git_remote", True, f"Configured Git remotes: {', '.join(remotes)}."
            return "dev_git_remote", False, "No Git remotes configured."

        # 3. Git Confirmation-Gated Commands (Commit, Push, Pull, Checkout, Merge)
        if lower.startswith("git commit") or lower.startswith("commit changes"):
            msg_match = re.search(r"commit(?:\s+with\s+message)?(?:\s+changes)?\s*[:\"']?(.*?)[\"']?$", lower)
            commit_msg = msg_match.group(1).strip() if msg_match else "Update from MacAssistant"
            self._pending_confirmation = {
                "action": "git_commit",
                "args": {"repo_path": repo_path, "message": commit_msg}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return (
                "dev_confirmation_required",
                True,
                f"{salutation}, please confirm: do you want me to commit uncommitted files in {repo_path.name} with message '{commit_msg}'?"
            )

        if lower.startswith("git push") or "push commits" in lower:
            self._pending_confirmation = {
                "action": "git_push",
                "args": {"repo_path": repo_path}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return (
                "dev_confirmation_required",
                True,
                f"{salutation}, please confirm: do you want me to push local commits to origin for {repo_path.name}?"
            )

        if lower.startswith("git pull") or "pull remote" in lower or "pull changes" in lower:
            self._pending_confirmation = {
                "action": "git_pull",
                "args": {"repo_path": repo_path}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return (
                "dev_confirmation_required",
                True,
                f"{salutation}, please confirm: do you want me to pull remote updates into {repo_path.name}?"
            )

        if lower.startswith("git checkout") or lower.startswith("switch branch"):
            branch_target = lower.replace("git checkout", "").replace("switch branch to", "").replace("switch branch", "").strip()
            self._pending_confirmation = {
                "action": "git_checkout",
                "args": {"repo_path": repo_path, "branch_name": branch_target}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return (
                "dev_confirmation_required",
                True,
                f"{salutation}, please confirm: switch {repo_path.name} branch to '{branch_target}'?"
            )

        # 4. Flutter Operations
        if any(k in lower for k in ["flutter doctor", "check flutter"]):
            res = FlutterManager.doctor(repo_path)
            summary = "Doctor scan complete. Check terminal for warnings." if res.success else "Flutter doctor found issues."
            return "dev_flutter_doctor", res.success, summary

        if any(k in lower for k in ["flutter analyze", "analyze flutter"]):
            res = FlutterManager.analyze(repo_path)
            msg = "Flutter analysis passed with zero errors." if res.success else "Flutter analysis reported issues."
            return "dev_flutter_analyze", res.success, msg

        if any(k in lower for k in ["flutter test", "run flutter tests"]):
            res = FlutterManager.test(repo_path)
            msg = "All Flutter tests passed successfully." if res.success else "Flutter tests failed or reported errors."
            return "dev_flutter_test", res.success, msg

        if any(k in lower for k in ["flutter pub get", "get flutter packages", "install flutter dependencies"]):
            self._pending_confirmation = {
                "action": "flutter_pub_get",
                "args": {"project_path": repo_path}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return "dev_confirmation_required", True, f"{salutation}, please confirm: download Flutter packages for {repo_path.name}?"

        if any(k in lower for k in ["build apk", "flutter build apk"]):
            self._pending_confirmation = {
                "action": "flutter_build_apk",
                "args": {"project_path": repo_path}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return "dev_confirmation_required", True, f"{salutation}, please confirm: trigger release APK compilation for {repo_path.name}?"

        if any(k in lower for k in ["build ipa", "flutter build ipa", "build ios"]):
            self._pending_confirmation = {
                "action": "flutter_build_ipa",
                "args": {"project_path": repo_path}
            }
            salutation = "Sir" if persona.lower() == "jarvis" else "Boss"
            return "dev_confirmation_required", True, f"{salutation}, please confirm: trigger release IPA compilation for {repo_path.name}?"

        # 5. Python Operations
        if any(k in lower for k in ["detect venv", "check python venv", "virtual environment"]):
            venv_dir, py_bin = PythonManager.detect_venv(repo_path)
            if venv_dir:
                return "dev_python_venv", True, f"Found virtual environment at {venv_dir.name} using Python binary."
            return "dev_python_venv", True, "No local virtual environment folder found; using default Python."

        if any(k in lower for k in ["run pytest", "run python tests", "run unit tests", "run tests"]):
            res = PythonManager.run_pytest(repo_path)
            msg = "Pytest executed cleanly with all tests passing." if res.success else "Tests completed with failures or errors."
            return "dev_python_pytest", res.success, msg

        # 6. Log Inspector & Error Analysis
        if any(k in lower for k in ["inspect logs", "check error logs", "check error log", "show recent errors", "recent errors in logs"]):
            summary = LogInspector.get_summary_speech()
            return "dev_inspect_logs", True, summary

        if any(k in lower for k in ["analyze error", "diagnose error", "explain error", "debug error"]):
            # Pull latest error from log inspector and run Ollama diagnostics
            log_data = LogInspector.inspect_file(LogInspector.DEFAULT_LOGS[0], max_lines=50)
            errors = log_data.get("errors", [])
            err_snippet = "\n".join(errors[-3:]) if errors else raw
            diagnosis = self.error_analyzer.analyze_error(err_snippet, context=repo_path.name)
            return "dev_error_analyzer", True, diagnosis

        return None

    def _execute_confirmed_action(self, action: str, args: Dict[str, Any], persona: str) -> Tuple[str, bool, str]:
        """Executes a previously confirmation-gated developer action."""
        salutation = "Sir" if persona.lower() == "jarvis" else "Boss"

        if action == "git_commit":
            res = GitManager.commit(args["repo_path"], args["message"], confirmed=True)
            if res.success:
                return "dev_git_commit", True, f"{salutation}, commit completed successfully."
            return "dev_git_commit", False, f"Commit failed: {res.stderr}"

        if action == "git_push":
            res = GitManager.push(args["repo_path"], confirmed=True)
            if res.success:
                return "dev_git_push", True, f"{salutation}, push to remote completed successfully."
            return "dev_git_push", False, f"Push failed: {res.stderr}"

        if action == "git_pull":
            res = GitManager.pull(args["repo_path"], confirmed=True)
            if res.success:
                return "dev_git_pull", True, f"{salutation}, pulled remote changes successfully."
            return "dev_git_pull", False, f"Pull failed: {res.stderr}"

        if action == "git_checkout":
            res = GitManager.checkout_branch(args["repo_path"], args["branch_name"], confirmed=True)
            if res.success:
                return "dev_git_checkout", True, f"{salutation}, switched branch to {args['branch_name']}."
            return "dev_git_checkout", False, f"Checkout failed: {res.stderr}"

        if action == "flutter_pub_get":
            res = FlutterManager.pub_get(args["project_path"], confirmed=True)
            if res.success:
                return "dev_flutter_pub_get", True, f"{salutation}, Flutter packages downloaded successfully."
            return "dev_flutter_pub_get", False, f"Pub get failed: {res.stderr}"

        if action == "flutter_build_apk":
            res = FlutterManager.build_apk(args["project_path"], confirmed=True)
            if res.success:
                return "dev_flutter_build_apk", True, f"{salutation}, release APK build succeeded."
            return "dev_flutter_build_apk", False, f"Build failed: {res.stderr}"

        if action == "flutter_build_ipa":
            res = FlutterManager.build_ipa(args["project_path"], confirmed=True)
            if res.success:
                return "dev_flutter_build_ipa", True, f"{salutation}, release IPA build succeeded."
            return "dev_flutter_build_ipa", False, f"Build failed: {res.stderr}"

        return "dev_unknown_action", False, f"Unknown action: {action}"

