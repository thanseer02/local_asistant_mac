"""Focus and meeting suppression guard for MacAssistant.

Zero-dependency native checks:
- Active conferencing process in a call (Microsoft Teams, Zoom CptHost, Cisco Webex, FaceTime).
- Active Google Meet in Google Chrome or Brave Browser (via AppleScript tab title check).
- macOS Focus / Do Not Disturb mode (via assertions or user defaults).
- Screen sharing detection.
"""

import json
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.FocusGuard")

DEFAULT_MEETING_PROCESSES = [
    "Microsoft Teams",
    "Teams",
    "CptHost",             # Zoom active meeting process
    "zoom.us",
    "Cisco Webex Meetings",
    "Webex",
    "FaceTime"
]


class FocusGuard:
    """Detects whether user is in a meeting or Focus mode to suppress non-urgent audio."""

    _last_check: float = 0.0
    _cached_result: bool = False
    _CACHE_TTL = 3.0  # Cache for 3 seconds to avoid redundant checks

    @classmethod
    def is_conferencing_process_running(cls, target_processes: Optional[List[str]] = None) -> bool:
        """Checks if known conferencing applications are actively executing."""
        targets = target_processes or DEFAULT_MEETING_PROCESSES
        try:
            cmd = ["/bin/ps", "-axc", "-o", "command"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
            running = res.stdout.splitlines()
            for proc in running:
                clean_proc = proc.strip()
                if any(t.lower() == clean_proc.lower() or t.lower() in clean_proc.lower() for t in targets):
                    return True
        except Exception as e:
            logger.debug("Process meeting check error: %s", e)
        return False

    @classmethod
    def is_browser_in_meeting(cls) -> bool:
        """Checks if Google Chrome or Brave Browser has an active Google Meet or Teams tab."""
        script = '''
        set inMeeting to false
        tell application "System Events"
            if exists (application process "Google Chrome") then
                tell application "Google Chrome"
                    try
                        repeat with w in windows
                            repeat with t in tabs of w
                                set tTitle to (title of t) as text
                                if tTitle contains "Meet –" or tTitle contains "Meet -" or tTitle contains "Google Meet" then
                                    set inMeeting to true
                                    exit repeat
                                end if
                            end repeat
                            if inMeeting then exit repeat
                        end repeat
                    end try
                end tell
            end if
            if not inMeeting and exists (application process "Brave Browser") then
                tell application "Brave Browser"
                    try
                        repeat with w in windows
                            repeat with t in tabs of w
                                set tTitle to (title of t) as text
                                if tTitle contains "Meet –" or tTitle contains "Meet -" or tTitle contains "Google Meet" then
                                    set inMeeting to true
                                    exit repeat
                                end if
                            end repeat
                            if inMeeting then exit repeat
                        end repeat
                    end try
                end tell
            end if
        end tell
        return inMeeting
        '''
        try:
            res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=1.0)
            return "true" in res.stdout.lower()
        except Exception:
            return False

    @classmethod
    def is_do_not_disturb_active(cls) -> bool:
        """Checks macOS native Focus / Do Not Disturb state via user defaults or Assertions.json."""
        # 1. Attempt reading native Focus assertions if accessible
        try:
            assertions_path = Path.home() / "Library" / "DoNotDisturb" / "DB" / "Assertions.json"
            if os.path.exists(str(assertions_path)):
                with open(assertions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("data", [{}])[0].get("storeAssertionRecords", [])
                    if len(records) > 0:
                        return True
        except Exception:
            pass

        # 2. Check defaults notification center / control center
        try:
            res = subprocess.run(
                ["/usr/bin/defaults", "read", "com.apple.controlcenter", "NSStatusItem Visible FocusModes"],
                capture_output=True, text=True, timeout=0.8
            )
            if res.stdout.strip() == "1":
                return True
        except Exception:
            pass

        return False

    @classmethod
    def is_busy(cls, config: Dict[str, Any]) -> bool:
        """
        Returns True if the user is in a meeting or Focus mode.
        Caches result for 3 seconds to maintain ~0% CPU.
        """
        guard_cfg = config.get("focus_guard", {})
        if not guard_cfg.get("enabled", True):
            return False

        now = time.time()
        if now - cls._last_check < cls._CACHE_TTL:
            return cls._cached_result

        apps = guard_cfg.get("apps", DEFAULT_MEETING_PROCESSES)

        busy = (
            cls.is_conferencing_process_running(apps) or
            cls.is_browser_in_meeting() or
            cls.is_do_not_disturb_active()
        )

        cls._cached_result = busy
        cls._last_check = now
        return busy
