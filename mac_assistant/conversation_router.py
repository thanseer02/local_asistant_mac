"""Intelligent conversation router distinguishing Conversation vs Action mode with Ollama."""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .application_launcher_service import ApplicationLauncherService
from .conversation_memory import ConversationMemory
from .file_search import FileSearchService
from .ollama_client import OllamaClient

logger = logging.getLogger("MacAssistant.ConversationRouter")


class ConversationRouter:
    """
    Intelligent Request Router:
    1. Handles CONVERSATION MODE (Ollama local LLM with multi-turn memory).
    2. Handles ACTION MODE (strict allowlist of authorized macOS tools).
    3. Handles CAPABILITIES & HELP requests dynamically.
    4. Enforces safety and requires explicit confirmation for destructive actions.
    5. Never outputs robotic rejection messages like 'That action is not in my allowlist.'
    """

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        memory: Optional[ConversationMemory] = None,
        request_confirmation_cb: Optional[Callable[[str], bool]] = None
    ):
        self.ollama = ollama_client or OllamaClient()
        self.memory = memory or ConversationMemory(max_turns=10)
        self.request_confirmation = request_confirmation_cb

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
                "Find general documents in your workspace"
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
                "Remember previous context across follow-up questions"
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
        prefix = "Sir, " if persona.lower() == "jarvis" else ""

        if not lower:
            return "empty", False, "I'm listening. How can I help?"

        # 0. Clean leading wake word if present
        for wake in ["hey jarvis", "hey friday", "jarvis", "friday", "please"]:
            if lower.startswith(wake):
                lower = lower[len(wake):].strip(", ").strip()
                raw = raw[len(wake):].strip(", ").strip()

        # Check pure wake-call salutations
        if lower in ["", "hello", "hi", "hey", "are you there", "you there", "wake up"]:
            reply = "I'm right here. What can I do for you?" if not prefix else f"{prefix}standing by. How may I assist?"
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

        # 3. DIRECT ACTION MODE CHECKS (Deterministic fast-path for Mac controls)
        # 3.1 Date & Time
        if any(k in lower for k in ["what time is it", "what's the time", "current time", "what day is today", "what is today's date", "date and time"]):
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d")
            return "check_datetime", True, f"The time is {time_str} on {date_str}."

        # 3.2 Battery Status
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

        # 3.3 Disk Space
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

        # 3.4 Open Application (Test 4 requirement)
        if re.search(r"^(open|launch|start)\s+", lower):
            app_target = re.sub(r"^(open|launch|start)\s+(the\s+)?", "", lower).strip()
            ok, msg = ApplicationLauncherService.launch(app_target)
            if ok:
                return "open_application", True, f"{prefix}{msg}"
            # If not in allowlist, do NOT give robotic rejection - fallback to conversational check or polite explanation
            logger.info("Application '%s' not directly matched in allowlist. Checking general intent...", app_target)

        # 3.5 Flutter Project Search
        if any(k in lower for k in ["flutter project", "flutter projects", "find flutter", "search flutter"]):
            projects = FileSearchService.find_flutter_projects(limit=3)
            if projects:
                names = ", ".join([p.name for p in projects])
                return "find_flutter", True, f"Found {len(projects)} Flutter projects: {names}."
            return "find_flutter", True, "I couldn't find any active Flutter projects in your workspace."

        # 3.6 PDF Search
        if "pdf" in lower and any(k in lower for k in ["find", "search", "show", "locate", "get"]):
            kw_match = re.search(r'(?:find|search|locate)?\s*(?:for)?\s*([a-zA-Z0-9_\-]+)\s+pdf', lower)
            keyword = kw_match.group(1) if (kw_match and kw_match.group(1) not in ["any", "all", "the", "my"]) else None
            pdfs = FileSearchService.find_pdfs(keyword=keyword, limit=3)
            if pdfs:
                names = ", ".join([p.name for p in pdfs])
                return "find_pdf", True, f"Found {len(pdfs)} matching PDF documents: {names}."
            return "find_pdf", True, "No matching PDF files were found."

        # 3.7 Stop Listening / Silence
        if any(lower == phrase or lower.startswith(phrase) for phrase in ["stop listening", "go to sleep", "sleep mode", "mute yourself"]):
            return "stop_listening", True, "Pausing voice listening now."

        # 3.8 Memory Clear
        if any(k in lower for k in ["clear history", "clear memory", "forget what we talked about", "new topic"]):
            self.memory.clear()
            return "clear_memory", True, "I've cleared our recent conversation history. What would you like to discuss next?"

        # 4. CONVERSATION MODE (Local Ollama with Multi-Turn Memory)
        # All conversational inputs (greetings, explanations, random facts, casual remarks) go here.
        # NEVER reject with "not in allowlist"
        system_prompt = self._build_conversational_system_prompt(persona)

        # Check Ollama availability
        if not self.ollama.is_available():
            logger.warning("Ollama daemon is not responding on http://localhost:11434.")
            # Friendly graceful fallback instead of robotic allowlist error
            if any(k in lower for k in ["how are you", "what's up", "good morning", "hello", "hi"]):
                return "conversation_fallback", True, "I'm doing well, thank you! Ready to help you with your Mac."
            return (
                "conversation_offline",
                False,
                "Conversational mode is temporarily unavailable because the local AI model is starting up. "
                "You can still ask me to open apps or search files."
            )

        # Append user message to history
        self.memory.add_user_message(raw)
        messages = self.memory.get_context_messages(system_prompt)

        logger.info("Routing to local Ollama (history: %d messages)...", len(messages))
        reply = self.ollama.chat(messages, temperature=0.7, max_tokens=150)

        if reply:
            cleaned_reply = self._clean_conversational_reply(reply)
            self.memory.add_assistant_message(cleaned_reply)
            return "conversation", True, cleaned_reply

        # Fallback if model returned empty
        return "conversation_ambiguous", True, "I'm following along. Could you tell me a little more?"

    def _build_conversational_system_prompt(self, persona: str) -> str:
        """Constructs prompt ensuring concise, natural, human responses."""
        if persona.lower() == "jarvis":
            persona_desc = "You are J.A.R.V.I.S., a knowledgeable, calm, and articulate AI companion for macOS."
        else:
            persona_desc = "You are F.R.I.D.A.Y., a friendly, bright, capable, and natural conversational companion for macOS."

        return (
            f"{persona_desc}\n"
            "Guidelines for speaking:\n"
            "1. Respond conversationally and warmly in 1 to 3 short sentences.\n"
            "2. Never use bullet points, markdown bold asterisks, code blocks, or technical symbols; speak like a human.\n"
            "3. Understand conversational context and follow-up questions from previous messages.\n"
            "4. Do not start every sentence with 'Sir' or 'Boss'. Address the user naturally.\n"
            "5. If the user asks a broad topic, give a crisp, interesting summary and optionally ask a natural follow-up.\n"
        )

    def _clean_conversational_reply(self, text: str) -> str:
        """Strips markdown asterisks, hashes, and formatting that sounds robotic when spoken."""
        t = re.sub(r"[*_#`~\[\]]", "", text)
        t = re.sub(r"https?://\S+", "", t)
        t = re.sub(r"\n+", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t
