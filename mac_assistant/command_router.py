"""Command router that normalizes spoken intents to allowlisted safe actions."""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .application_launcher_service import ApplicationLauncherService
from .file_search import FileSearchService

logger = logging.getLogger("MacAssistant.CommandRouter")


class CommandRouter:
    """Normalizes natural phrasings and routes them safely to allowed actions."""

    def __init__(self, request_confirmation_cb: Optional[Callable[[str], bool]] = None):
        self.request_confirmation = request_confirmation_cb

    def route(self, utterance: str, persona: str = "friday") -> Tuple[str, bool, str]:
        """
        Interprets natural language commands and maps to actions.
        Returns: (intent_name: str, success: bool, spoken_response: str)
        """
        raw = utterance.lower().strip()
        prefix = "Sir, "

        # 0. Check pure wake-call salutations (calling Friday or Jarvis)
        if raw in [
            "friday", "hey friday", "hello friday", "hi friday",
            "jarvis", "hey jarvis", "hello jarvis", "hi jarvis",
            "are you there", "you there", "wake up"
        ]:
            if persona.lower() == "jarvis":
                wake_replies = [
                    f"{prefix}at your service. How may I assist you?",
                    f"Yes, {prefix.strip(', ')}? Standing by.",
                    f"{prefix}Jarvis online. What is your command?",
                ]
            else:
                wake_replies = [
                    f"{prefix}I'm here! What do you need?",
                    f"Yes, {prefix.strip(', ')}? How can I help?",
                    f"{prefix}Friday listening! What's up?",
                    f"Right here, {prefix.strip(', ')}. Standing by.",
                ]
            import random
            return "wake_call", True, random.choice(wake_replies)

        # Clean leading wake word if followed by a command
        for wake in ["hey jarvis", "hey friday", "jarvis", "friday", "please"]:
            if raw.startswith(wake):
                raw = raw[len(wake):].strip(", ").strip()

        # 1. Intent: STOP LISTENING / SLEEP / PAUSE
        if any(raw == phrase or raw.startswith(phrase) for phrase in [
            "stop listening", "go to sleep", "sleep mode", "mute yourself", "pause listening", "stop voice"
        ]):
            return "stop_listening", True, f"{prefix}I am pausing voice listening now."

        # 2. Intent: SYSTEM EXIT
        if any(raw == phrase for phrase in ["exit", "quit", "terminate", "goodbye"]):
            return "exit", True, f"{prefix}shutting down assistant service."

        # 3. Intent: LOCK SCREEN
        if any(k in raw for k in ["lock my mac", "lock the screen", "lock mac", "lock computer", "lock screen"]):
            logger.info("Executing safe lock screen")
            try:
                subprocess.Popen([
                    "/usr/bin/osascript", "-e",
                    'tell application "System Events" to keystroke "q" using {command down, control down}'
                ])
                return "lock_screen", True, f"{prefix}locking your console."
            except Exception as e:
                return "lock_screen", False, f"{prefix}I could not lock the console."

        # 4. Intent: DATE & TIME
        if any(k in raw for k in ["what time is it", "what's the time", "current time", "what day is today", "what is today's date", "date and time"]):
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d")
            return "check_datetime", True, f"{prefix}the time is {time_str} on {date_str}."

        # 5. Intent: SEARCH FLUTTER PROJECTS
        if any(k in raw for k in ["flutter project", "flutter projects", "find flutter", "search flutter"]):
            logger.info("Routing Flutter project search")
            projects = FileSearchService.find_flutter_projects(limit=3)
            if projects:
                names = ", ".join([p.name for p in projects])
                return "find_flutter", True, f"{prefix}I found {len(projects)} Flutter projects: {names}."
            return "find_flutter", True, f"{prefix}I could not find any active Flutter projects in your documents."

        # 6. Intent: SEARCH PDF FILES
        if "pdf" in raw:
            logger.info("Routing PDF search")
            # Extract keyword if specified (e.g. 'find invoice pdfs' or 'search for report pdf')
            keyword = None
            kw_match = re.search(r'(?:find|search|locate)?\s*(?:for)?\s*([a-zA-Z0-9_\-]+)\s+pdf', raw)
            if kw_match and kw_match.group(1) not in ["any", "all", "the", "my"]:
                keyword = kw_match.group(1)

            pdfs = FileSearchService.find_pdfs(keyword=keyword, limit=3)
            if pdfs:
                names = ", ".join([p.name for p in pdfs])
                return "find_pdf", True, f"{prefix}I found {len(pdfs)} matching PDF documents: {names}."
            return "find_pdf", True, f"{prefix}no matching PDF files were found."

        # 7. Intent: OPEN APPLICATION
        if raw.startswith("open ") or raw.startswith("launch ") or raw.startswith("start "):
            app_target = re.sub(r'^(open|launch|start)\s+(the\s+)?', '', raw).strip()
            ok, msg = ApplicationLauncherService.launch(app_target)
            return "open_application", ok, f"{prefix}{msg}"

        # 8. Intent: TAKE QUICK NOTE
        if any(k in raw for k in ["take a note", "take a quick note", "write down", "note that"]):
            note_content = re.sub(r'^(take a note|take a quick note|write down|note that)\s*', '', raw).strip()
            if not note_content:
                note_content = "Quick note recorded at " + datetime.now().strftime("%I:%M %p")

            notes_file = Path.home() / "Desktop" / "Assistant_Notes.txt"
            fallback_file = Path(__file__).resolve().parent.parent / "Assistant_Notes.txt"
            target = notes_file if notes_file.parent.exists() else fallback_file

            try:
                with open(target, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {note_content.capitalize()}\n")
                return "take_note", True, f"{prefix}note saved to your desktop."
            except Exception:
                return "take_note", False, f"{prefix}could not write the note."

        # 9. Intent: VOLUME CONTROL
        if "volume" in raw:
            if "mute" in raw:
                subprocess.run(["/usr/bin/osascript", "-e", "set volume with output muted"], check=False)
                return "volume_control", True, f"{prefix}audio muted."
            elif "up" in raw or "increase" in raw:
                subprocess.run(["/usr/bin/osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 15)"], check=False)
                return "volume_control", True, f"{prefix}raising volume."
            elif "down" in raw or "lower" in raw:
                subprocess.run(["/usr/bin/osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 15)"], check=False)
                return "volume_control", True, f"{prefix}lowering volume."

        # 10. Fallback - Reject arbitrary execution
        logger.info("Unrecognized command rejected: '%s'", utterance)
        return "unknown", False, f"{prefix}I heard: '{utterance}', but that action is not in my allowlist."
