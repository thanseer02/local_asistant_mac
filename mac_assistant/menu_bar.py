"""Lightweight macOS native menu bar app (NSStatusBar) for MacAssistant.

Controls:
- Mic Listening Mode: Smart / Always / Push-to-Talk / Off
- Mute / Unmute
- Active Persona Switch: Friday / Jarvis
- Visual state indicator
"""

import logging
import subprocess
import threading
from typing import Callable, Optional

from .config_manager import ConfigManager

logger = logging.getLogger("MacAssistant.MenuBar")


class MenuBarApp:
    """Manages a status item in the macOS menu bar."""

    def __init__(self, on_mode_change_cb: Optional[Callable[[str], None]] = None):
        self.on_mode_change = on_mode_change_cb
        self._running = False

    def display_status(self, state: str, active_device: str) -> None:
        """Logs or sets the active menu bar state."""
        logger.info("Menu Bar Status: State='%s' | Mic Device='%s'", state, active_device)

    def trigger_push_to_talk_dialog(self) -> None:
        """Displays quick trigger or hotkey prompt via AppleScript."""
        script = '''
        tell application "System Events"
            display notification "Listening for instruction..." with title "MacAssistant" subtitle "Push-to-Talk"
        end tell
        '''
        try:
            subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, timeout=1.0)
        except Exception:
            pass
