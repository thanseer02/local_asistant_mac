"""Safe execution service for macOS automation tasks."""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from modules.services.logging_service import logger


class MacAutomationService:
    """
    Executes authorized macOS system automation commands.
    Strictly uses list-based subprocess execution (never shell=True).
    Prevents execution of arbitrary or unsafe commands.
    """

    ALLOWED_APPLICATIONS: Dict[str, str] = {
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "visual studio code": "Visual Studio Code",
        "terminal": "Terminal",
        "iterm": "iTerm",
        "iterm2": "iTerm",
        "brave": "Brave Browser",
        "brave browser": "Brave Browser",
        "spotify": "Spotify",
        "slack": "Slack",
        "antigravity": "Antigravity",
        "finder": "Finder",
        "calendar": "Calendar",
        "reminders": "Reminders",
        "notes": "Notes",
        "system settings": "System Settings",
        "settings": "System Settings",
        "calculator": "Calculator",
    }

    @classmethod
    def open_application(cls, app_name: str) -> Tuple[bool, str]:
        """Launches an allowlisted macOS application."""
        normalized = app_name.strip().lower()
        target = cls.ALLOWED_APPLICATIONS.get(normalized)

        if not target:
            # Check if any key is contained in normalized
            for key, val in cls.ALLOWED_APPLICATIONS.items():
                if key in normalized:
                    target = val
                    break

        if not target:
            logger.warning(f"Unauthorized application launch request: '{app_name}'")
            return False, f"Application '{app_name}' is not in the authorized allowlist."

        try:
            logger.info(f"Opening application: {target}")
            subprocess.run(["/usr/bin/open", "-a", target], check=True, timeout=5)
            return True, f"Opened {target} successfully."
        except Exception as e:
            logger.error(f"Failed opening application {target}: {e}")
            return False, f"Failed to open {target}: {str(e)}"

    @classmethod
    def open_folder(cls, folder_path: str) -> Tuple[bool, str]:
        """Opens a local directory in macOS Finder."""
        path = Path(folder_path).expanduser().resolve()
        if not path.exists():
            return False, f"Folder does not exist: {folder_path}"
        if not path.is_dir():
            return False, f"Path is not a directory: {folder_path}"

        try:
            subprocess.run(["/usr/bin/open", str(path)], check=True, timeout=5)
            return True, f"Opened folder: {path.name}"
        except Exception as e:
            return False, f"Failed opening folder: {str(e)}"

    @classmethod
    def get_system_battery(cls) -> Dict[str, str]:
        """Checks battery percentage and charging status via pmset."""
        try:
            out = subprocess.check_output(["/usr/bin/pmset", "-g", "batt"], text=True)
            return {"raw": out.strip()}
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    def get_volume(cls) -> Optional[int]:
        """Returns current macOS volume level (0-100)."""
        try:
            cmd = ["osascript", "-e", "output volume of (get volume settings)"]
            val = subprocess.check_output(cmd, text=True).strip()
            return int(val)
        except Exception:
            return None

    @classmethod
    def set_volume(cls, percent: int) -> bool:
        """Sets macOS system output volume (0-100)."""
        clamped = max(0, min(100, int(percent)))
        try:
            cmd = ["osascript", "-e", f"set volume output volume {clamped}"]
            subprocess.run(cmd, check=True)
            return True
        except Exception as e:
            logger.error(f"Failed setting volume: {e}")
            return False
