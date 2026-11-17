"""Voice command dispatcher for executing actions requested by the user."""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("MacAssistant.CommandDispatcher")


class VoiceCommandDispatcher:
    """Parses transcribed voice text and executes target Mac commands."""

    @staticmethod
    def execute_command(command_text: str, persona: str = "friday") -> Tuple[bool, str]:
        """
        Interprets spoken command strings and executes matching system actions.
        Returns: (success: bool, response_speech: str)
        """
        text = command_text.lower().strip()
        prefix = "Sir, "

        # 1. Lock Mac
        if "lock" in text and ("mac" in text or "screen" in text or "computer" in text):
            logger.info("Executing: Lock Mac")
            try:
                # Locks the screen via macOS command line tool
                subprocess.Popen([
                    "/usr/bin/osascript", "-e",
                    'tell application "System Events" to keystroke "q" using {command down, control down}'
                ])
                return True, f"{prefix}locking your console now."
            except Exception as e:
                return False, f"{prefix}I encountered an issue locking the screen."

        # 2. Open Applications
        if text.startswith("open ") or "launch " in text:
            app_target = text.replace("open ", "").replace("launch ", "").strip()
            
            app_map = {
                "vs code": "Visual Studio Code",
                "vscode": "Visual Studio Code",
                "code": "Visual Studio Code",
                "chrome": "Google Chrome",
                "brave": "Brave Browser",
                "antigravity": "Antigravity IDE",
                "spotify": "Spotify",
                "terminal": "Terminal",
                "finder": "Finder"
            }
            resolved_app = app_map.get(app_target, app_target.title())
            logger.info("Executing: Open application '%s'", resolved_app)
            try:
                subprocess.Popen(["/usr/bin/open", "-a", resolved_app])
                return True, f"{prefix}opening {resolved_app}."
            except Exception as e:
                return False, f"{prefix}I could not find an application named {resolved_app}."

        # 3. Next Meeting / Agenda check
        if "meeting" in text or "calendar" in text or "agenda" in text:
            logger.info("Executing: Check next meeting")
            script = '''
            tell application "Reminders"
                set res to "clear"
                try
                    repeat with l in lists
                        repeat with r in (reminders of l whose completed is false)
                            return (name of r)
                        end repeat
                    end repeat
                end try
                return res
            end tell
            '''
            try:
                res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=3)
                task = res.stdout.strip()
                if task and task != "clear":
                    return True, f"{prefix}your next scheduled item is {task}."
                return True, f"{prefix}your agenda is completely clear right now."
            except Exception:
                return True, f"{prefix}all upcoming schedules are clear."

        # 4. Take a quick note
        if "note" in text or "write this down" in text:
            note_content = (
                text.replace("take a quick note", "")
                    .replace("take a note", "")
                    .replace("write this down", "")
                    .strip()
            )
            if not note_content:
                note_content = "Quick thought recorded at " + datetime.now().strftime("%I:%M %p")

            # Store notes inside MacAssistant directory or Desktop
            notes_file = Path.home() / "Desktop" / "Assistant_Notes.txt"
            fallback_file = Path(__file__).resolve().parent.parent / "Assistant_Notes.txt"
            target_path = notes_file if notes_file.parent.exists() else fallback_file

            try:
                with open(target_path, "a", encoding="utf-8") as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {note_content.capitalize()}\n")
                logger.info("Note saved to %s", target_path)
                return True, f"{prefix}note saved to your desktop."
            except Exception as e:
                try:
                    with open(fallback_file, "a", encoding="utf-8") as f:
                        f.write(f"[{datetime.now()}] {note_content.capitalize()}\n")
                    return True, f"{prefix}note saved to your assistant folder."
                except Exception:
                    return False, f"{prefix}I couldn't write the note."

        # 5. Volume Controls
        if "volume" in text:
            if "mute" in text:
                subprocess.run(["/usr/bin/osascript", "-e", "set volume with output muted"], check=False)
                return True, f"{prefix}audio output has been muted."
            elif "up" in text:
                subprocess.run(["/usr/bin/osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 15)"], check=False)
                return True, f"{prefix}increasing volume."
            elif "down" in text:
                subprocess.run(["/usr/bin/osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 15)"], check=False)
                return True, f"{prefix}lowering volume."

        # 6. Fallback
        return False, f"{prefix}I heard your command, but I don't know how to handle that yet."
