"""Safe application launcher utilizing strictly allowlisted apps and safe argument lists."""

import logging
import subprocess
from typing import Dict, List, Optional

logger = logging.getLogger("MacAssistant.AppLauncherService")

# Safe allowlist of application aliases and executable bundle names
APP_ALLOWLIST: Dict[str, str] = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "brave": "Brave Browser",
    "brave browser": "Brave Browser",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "iterm2": "iTerm",
    "antigravity": "Antigravity IDE",
    "antigravity ide": "Antigravity IDE",
    "spotify": "Spotify",
    "finder": "Finder",
    "calendar": "Calendar",
    "notes": "Notes",
    "reminders": "Reminders",
    "slack": "Slack"
}


class ApplicationLauncherService:
    """Safely launches macOS applications without arbitrary shell execution."""

    @classmethod
    def get_supported_apps(cls) -> List[str]:
        return list(set(APP_ALLOWLIST.values()))

    @classmethod
    def launch(cls, target_name: str) -> tuple[bool, str]:
        """
        Launches an allowlisted application using safe subprocess argument lists.
        Returns (success: bool, spoken_message: str).
        """
        clean_target = target_name.lower().strip()
        resolved_app = APP_ALLOWLIST.get(clean_target)

        if not resolved_app:
            logger.warning("Rejected application launch for non-allowlisted target: '%s'", target_name)
            return False, f"I am not authorized or configured to open {target_name}."

        logger.info("Safely launching application: '%s'", resolved_app)
        try:
            # Safe argument list - never shell=True
            subprocess.Popen(["/usr/bin/open", "-a", resolved_app])
            return True, f"Opening {resolved_app}."
        except Exception as e:
            logger.error("Failed launching %s: %s", resolved_app, e)
            return False, f"Could not launch {resolved_app}."
