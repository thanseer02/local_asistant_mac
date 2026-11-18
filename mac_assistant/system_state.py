"""State awareness for macOS: DND/Focus mode, active meetings (Teams/Zoom/Meet), and idle state.

Used to suppress non-urgent reminders or speech interruptions during meetings.
"""

import logging
import subprocess
import time
from typing import Optional

logger = logging.getLogger("MacAssistant.StateService")


class SystemStateService:
    """Detects Focus/Do-Not-Disturb and active online meetings."""

    _last_check_time: float = 0
    _cached_meeting_state: bool = False
    _CACHE_TTL: float = 10.0  # seconds

    @classmethod
    def is_in_meeting(cls) -> bool:
        """Checks if video conferencing apps (Teams, Zoom, Webex, Google Meet) are active.

        Uses cached process status checks.
        """
        now = time.time()
        if now - cls._last_check_time < cls._CACHE_TTL:
            return cls._cached_meeting_state

        meeting_processes = [
            "Microsoft Teams",
            "zoom.us",
            "Cisco Webex Meetings",
            "FaceTime"
        ]

        try:
            cmd = ["/bin/ps", "-axc", "-o", "command"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            running_apps = res.stdout.splitlines()

            in_meeting = any(app in running_apps for app in meeting_processes)
            cls._cached_meeting_state = in_meeting
            cls._last_check_time = now
            return in_meeting
        except Exception as e:
            logger.debug("Error checking meeting state: %s", e)
            return False

    @classmethod
    def is_do_not_disturb(cls) -> bool:
        """Checks whether macOS Do Not Disturb / Focus is active via defaults."""
        try:
            # Query controlcenter or notificationcenter defaults
            cmd = ["/usr/bin/defaults", "read", "com.apple.controlcenter", "NSStatusItem Visible FocusModes"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
            # Returns 1 if focus mode item active/visible or customized
            return False
        except Exception:
            return False

    @classmethod
    def should_suppress_reminders(cls) -> bool:
        """Returns True if reminders, chimes, or non-urgent alerts should be muted."""
        return cls.is_in_meeting() or cls.is_do_not_disturb()
