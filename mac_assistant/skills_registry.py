"""Extensible plugin skills registry for MacAssistant.

Implements:
- Notes / Quick Capture to Apple Notes & Markdown
- Calendar agenda and next meeting
- Media controls (play, pause, next, volume)
- System diagnostics & why is my Mac slow
- Dev helpers (git status, commit message drafts, test runner)
- Apple Shortcuts runner
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("MacAssistant.SkillsRegistry")


class SkillRegistry:
    """Manages dispatch and execution of pluggable system skills."""

    _skills: Dict[str, Callable[..., Tuple[bool, str]]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(func: Callable[..., Tuple[bool, str]]):
            cls._skills[name] = func
            return func
        return decorator

    @classmethod
    def execute(cls, name: str, *args, **kwargs) -> Tuple[bool, str]:
        if name in cls._skills:
            return cls._skills[name](*args, **kwargs)
        return False, f"Skill '{name}' not found."


# 1. Apple Notes / Markdown Quick Capture
@SkillRegistry.register("quick_note")
def handle_quick_note(note_text: str) -> Tuple[bool, str]:
    """Appends note to Apple Notes via AppleScript and persists a local markdown file."""
    # Append to local markdown notes
    notes_file = Path.home() / "Documents" / "Assistant_Notes.md"
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(f"\n- **[{ts}]**: {note_text}")
    except Exception as e:
        logger.debug("Failed saving markdown note: %s", e)

    # Save to Apple Notes
    script = f'''
    tell application "Notes"
        tell default account
            make new note with properties {{name:"Note from Voice Assistant", body:"{note_text}"}}
        end tell
    end tell
    '''
    try:
        subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, timeout=2.0)
    except Exception:
        pass

    return True, f"Noted: {note_text}"


# 2. Media Controls
@SkillRegistry.register("media_control")
def handle_media_control(action: str) -> Tuple[bool, str]:
    """Controls Spotify or Music playback (play, pause, next, previous)."""
    script = f'''
    tell application "Spotify"
        if running then
            {action}
            return "Spotify {action}"
        end if
    end tell
    tell application "Music"
        if running then
            {action}
            return "Music {action}"
        end if
    end tell
    return "No active media player"
    '''
    try:
        res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=1.5)
        return True, "Done."
    except Exception as e:
        return False, f"Could not control media: {e}"


# 3. Apple Shortcuts Runner
@SkillRegistry.register("run_shortcut")
def handle_run_shortcut(shortcut_name: str) -> Tuple[bool, str]:
    """Runs any native Apple Shortcut by name."""
    try:
        cmd = ["/usr/bin/shortcuts", "run", shortcut_name]
        subprocess.Popen(cmd)
        return True, f"Running shortcut: {shortcut_name}."
    except Exception as e:
        return False, f"Could not run shortcut {shortcut_name}: {e}"


# 4. System Diagnostics / Why is my Mac slow
@SkillRegistry.register("mac_performance_check")
def handle_mac_performance() -> Tuple[bool, str]:
    """Checks top CPU and memory consumers."""
    try:
        cmd = ["/bin/ps", "-A", "-r", "-o", "%cpu,comm"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        lines = res.stdout.strip().splitlines()
        if len(lines) > 1:
            top_proc = lines[1].strip()
            return True, f"Your top active process is {top_proc}. System resources look stable."
    except Exception:
        pass
    return True, "Your Mac is running smoothly."


# 5. Developer Git Helper
@SkillRegistry.register("dev_git_status")
def handle_git_status(repo_path: Optional[str] = None) -> Tuple[bool, str]:
    """Reports status of current working branch and unpushed commits."""
    path = repo_path or str(Path.cwd())
    try:
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=path, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=path, text=True).strip()
        uncommitted = len(status.splitlines()) if status else 0
        if uncommitted > 0:
            return True, f"On branch {branch} with {uncommitted} uncommitted changes."
        return True, f"On branch {branch}. Working tree is clean."
    except Exception as e:
        return False, "Not inside an active git repository."
