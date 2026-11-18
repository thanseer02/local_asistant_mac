"""macOS system context collector: frontmost app, current project, git branch, and time."""

import logging
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.ContextAwareness")


class ContextAwarenessService:
    """Collects real-time macOS context for LLM prompt enhancement."""

    @staticmethod
    def get_frontmost_app() -> Optional[str]:
        """Gets the currently active application name via AppleScript."""
        script = '''
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
            return frontApp
        end tell
        '''
        try:
            res = subprocess.run(
                ["/usr/bin/osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            val = res.stdout.strip()
            return val if val else None
        except Exception:
            return None

    @staticmethod
    def get_git_info(workspace_dir: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Returns branch and status of current project if inside a git repo."""
        cwd = workspace_dir or str(Path.cwd())
        try:
            branch_res = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=1.0
            )
            branch = branch_res.stdout.strip()
            if branch:
                return {"branch": branch, "project": Path(cwd).name}
        except Exception:
            pass
        return None

    @classmethod
    def get_system_context_summary(cls, user_name: str = "Sir") -> str:
        """Returns a concise system prompt context injection."""
        app = cls.get_frontmost_app() or "Desktop"
        git = cls.get_git_info()
        now_str = time.strftime("%A, %B %d, %Y %I:%M %p")

        context = f"[Context: Time is {now_str}. User is {user_name}. Active app: {app}."
        if git:
            context += f" Git repo: {git['project']} (branch: {git['branch']})."
        context += "]"
        return context
