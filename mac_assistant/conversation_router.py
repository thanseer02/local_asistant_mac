"""Intelligent conversation router distinguishing Conversation vs Action mode with Friday & Jarvis personality engines.

Features:
- Fast rule-based commands with decorators/registry
- Long-term memory storage ("remember that...", "recall fact...")
- System context awareness (frontmost app, git branch, time of day)
- Voice controls for stop/quiet
- Snooze and custom timer support
- Safety confirmations
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.ai.conversation_manager import ConversationManager
from modules.personality.friday_personality import FridayPersonalityEngine
from modules.personality.jarvis_personality import JarvisPersonalityEngine
from .application_launcher_service import ApplicationLauncherService
from .config_manager import ConfigManager
from .context_service import ContextAwarenessService
from .file_search import FileSearchService
from .ollama_client import OllamaClient

logger = logging.getLogger("MacAssistant.ConversationRouter")


class ConversationRouter:
    """Intelligent Request Router:

    1. Action Mode (Direct rule-based execution for speed and low CPU).
    2. Fact Memory ("Remember that...", "What is my...").
    3. Tool/function calling and Ollama local conversation.
    4. Safe confirmation before destructive actions.
    """

    def __init__(
        self,
        ollama_client: Optional[OllamaClient] = None,
        conv_manager: Optional[ConversationManager] = None,
        request_confirmation_cb: Optional[Callable[[str], bool]] = None
    ):
        self._ollama = ollama_client
        self.conv_manager = conv_manager or ConversationManager()
        self.friday_engine = FridayPersonalityEngine()
        self.jarvis_engine = JarvisPersonalityEngine()
        self.request_confirmation = request_confirmation_cb

    @property
    def ollama(self) -> OllamaClient:
        """Lazy-load Ollama client on first use."""
        if self._ollama is None:
            self._ollama = OllamaClient()
        return self._ollama

    def _get_engine(self, persona: str):
        if persona.lower() == "jarvis":
            return self.jarvis_engine
        return self.friday_engine

    def get_registered_capabilities(self) -> Dict[str, List[str]]:
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
                "Adjust volume, stop or pause speech",
                "Lock screen securely"
            ],
            "Memory & Notes": [
                "Remember that [fact or note]",
                "What did I tell you to remember about [topic]?",
                "What did we just talk about?"
            ],
            "Conversational Companion": [
                "Explain software architecture, Flutter, Python, or engineering topics",
                "Tell jokes, random interesting facts, or suggest learning topics",
                "Remember previous context across follow-up questions"
            ]
        }

    def format_capabilities_speech(self) -> str:
        return (
            "I can control your Mac, remember notes, and chat naturally with you. "
            "For Mac automation, I can launch your applications like Chrome, VS Code, and Terminal; "
            "search for Flutter projects or PDF documents; check your battery, disk space, and time; "
            "or adjust your volume. "
            "In conversation mode, I can explain technical concepts, answer questions, and remember key facts for you."
        )

    def route(self, utterance: str, persona: str = "friday") -> Tuple[str, bool, str]:
        """Routes utterance intelligently between Action Mode, Memory, and Conversation Mode.

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

        # Stop / Quiet barge-in
        if lower in ["stop", "quiet", "shut up", "hush", "be quiet", "stop speaking", "pause"]:
            return "stop", True, ""

        # Persona switch
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

        # Wake call salutations
        if lower in ["", "hello", "hi", "hey", "are you there", "you there", "wake up"]:
            reply = active_engine.greetings.get_activation_greeting(persona=persona)
            return "wake_call", True, reply

        # 1. DESTRUCTIVE ACTIONS SAFETY GUARD
        if any(p in lower for p in ["delete all", "delete my files", "rm -rf", "format disk", "wipe system", "erase mac"]):
            logger.warning("Blocked destructive action request: '%s'", raw)
            return (
                "destructive_rejected",
                False,
                "Deleting system or user files is a high-risk destructive operation. "
                "I cannot execute that command without explicit administrator authorization and manual safety review."
            )

        # 2. CAPABILITIES & HELP REQUESTS
        if any(p in lower for p in [
            "what can you do", "show available commands", "what features do you have",
            "how can you help me", "list of commands", "what are you capable of", "help me"
        ]):
            return "capabilities", True, self.format_capabilities_speech()

        # 3. USER FACTS / NOTES MEMORY
        # Store fact: "remember that my key is value", "note that..."
        remember_match = re.search(r"^(?:please\s+)?(?:remember|note)\s+(?:that\s+)?(.+)", lower)
        if remember_match:
            fact_text = remember_match.group(1).strip()
            # Split key/value if possible
            key_words = fact_text.split()[:3]
            key = " ".join(key_words)
            if self.conv_manager.sqlite_memory:
                self.conv_manager.sqlite_memory.remember_fact(key, fact_text)
            if persona.lower() == "jarvis":
                return "remember_fact", True, f"Understood, Sir. I have committed that to permanent memory: {fact_text}."
            return "remember_fact", True, f"Got it! I'll remember that: {fact_text}."

        # Recall fact: "what did i ask you to remember", "recall fact"
        if any(k in lower for k in ["what did i tell you to remember", "what did i ask you to remember", "do you remember"]):
            if self.conv_manager.sqlite_memory:
                fact = self.conv_manager.sqlite_memory.recall_fact(lower)
                if fact:
                    return "recall_fact", True, f"Here is what I remember: {fact}."
            return "recall_fact", True, "I couldn't find a matching note in my memory."

        # 4. VOICE-BASED PERSONALITY & RECENT DISCUSSION MEMORY
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

        if any(k in lower for k in ["what did we just talk about", "recall our discussion", "what were we talking about", "recall memory"]):
            if self.conv_manager.sqlite_memory:
                recall = self.conv_manager.sqlite_memory.recall_last_discussion()
                if recall:
                    return "recall_memory", True, recall
            return "recall_memory", True, "We haven't discussed any topics in this session yet."

        if any(k in lower for k in ["clear history", "clear memory", "forget what we talked about", "new topic"]):
            self.conv_manager.clear()
            return "clear_memory", True, "I've cleared our conversation history from memory. What should we explore next?"

        # 5. DIRECT ACTION MODE CHECKS
        # Date & Time
        if any(k in lower for k in ["what time is it", "what's the time", "current time", "what day is today", "what is today's date", "date and time", "the time", "check the time", "check time"]):
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d")
            return "check_datetime", True, f"The time is {time_str} on {date_str}."

        # Battery Status
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

        # Disk Space
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

        # Open Application
        if re.search(r"^(open|launch|start)\s+", lower):
            app_target = re.sub(r"^(open|launch|start)\s+(the\s+)?", "", lower).strip()
            ok, msg = ApplicationLauncherService.launch(app_target)
            if ok:
                return "open_application", True, msg
            logger.info("Application '%s' not in direct allowlist. Checking general intent...", app_target)

        # Flutter Project Search
        if any(k in lower for k in ["flutter project", "flutter projects", "find flutter", "search flutter"]):
            projects = FileSearchService.find_flutter_projects(limit=3)
            if projects:
                names = ", ".join([p.name for p in projects])
                return "find_flutter", True, f"Found {len(projects)} Flutter projects: {names}."
            return "find_flutter", True, "I couldn't find any active Flutter projects in your workspace."

        # PDF Search
        if "pdf" in lower and any(k in lower for k in ["find", "search", "show", "locate", "get"]):
            kw_match = re.search(r'(?:find|search|locate)?\s*(?:for)?\s*([a-zA-Z0-9_\-]+)\s+pdf', lower)
            keyword = kw_match.group(1) if (kw_match and kw_match.group(1) not in ["any", "all", "the", "my"]) else None
            pdfs = FileSearchService.find_pdfs(keyword=keyword, limit=3)
            if pdfs:
                names = ", ".join([p.name for p in pdfs])
                return "find_pdf", True, f"Found {len(pdfs)} matching PDF documents: {names}."
            return "find_pdf", True, "No matching PDF files were found."

        # Stop Listening
        if any(lower == phrase or lower.startswith(phrase) for phrase in ["stop listening", "go to sleep", "sleep mode", "mute yourself"]):
            return "stop_listening", True, "Pausing voice listening now."

        # 6. CONVERSATION MODE WITH CONTEXT INJECTION (Ollama LLM)
        config = ConfigManager.load()
        user_name = config.get("user_name", "Sir")
        sys_context = ContextAwarenessService.get_system_context_summary(user_name=user_name)

        base_system_prompt = active_engine.build_system_prompt(user_utterance=raw)
        system_prompt = f"{base_system_prompt}\n{sys_context}\nKeep responses spoken, natural, concise (under 2 sentences), and free of markdown."

        # Check Ollama availability
        if not self.ollama.is_available():
            logger.warning("Ollama daemon is not responding on http://localhost:11434.")
            if any(k in lower for k in ["how are you", "what's up", "good morning", "hello", "hi"]):
                fallback = "At your service, Sir. Ready to assist with your Mac." if persona.lower() == "jarvis" else "I'm doing well, thank you! Ready to help you with your Mac."
                return "conversation_fallback", True, fallback
            return (
                "ollama_unavailable",
                False,
                f"I'm ready for Mac commands, but my conversational AI server isn't running on your Mac right now. You can run 'ollama serve' if you'd like to chat."
            )

        # Multi-turn history with context
        messages = self.conv_manager.get_chat_history()
        messages.append({"role": "user", "content": raw})

        logger.info("Dispatching query to Ollama LLM with active context: '%s'", raw)
        llm_reply = self.ollama.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.7
        )

        if llm_reply:
            cleaned = active_engine.formatter.format(llm_reply, persona=persona)
            cleaned = cleaned.replace("*", "").replace("#", "").replace("`", "").strip()
            self.conv_manager.add_turn("user", raw, intent="conversation")
            self.conv_manager.add_turn("assistant", cleaned, intent="conversation")
            return "conversation", True, cleaned

        return "error", False, "I had trouble generating a response. Please try again."
