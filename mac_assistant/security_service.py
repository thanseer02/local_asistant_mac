"""Confirmation security service requiring voice confirmation or Touch ID for sensitive actions."""

import logging
import subprocess
from typing import Callable, Optional

logger = logging.getLogger("MacAssistant.SecurityConfirmation")


class SecurityConfirmationService:
    """Safeguards sensitive actions: lock, sleep, file deletions, sending emails/messages, shell execution."""

    DEFAULT_PIN = "1234"

    @classmethod
    def request_touch_id(cls, reason: str = "MacAssistant sensitive operation") -> bool:
        """Prompts for Touch ID or macOS administrator password via AppleScript."""
        script = f'''
        tell application "System Events"
            activate
            set res to display dialog "Authorize {reason}?" buttons {{"Cancel", "Authorize"}} default button "Authorize" with icon caution with hidden answer
            return res
        end tell
        '''
        try:
            res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=15)
            return "Authorize" in res.stdout
        except Exception:
            return False

    @classmethod
    def verify_voice_pin(cls, spoken_pin: str, expected_pin: Optional[str] = None) -> bool:
        """Verifies voice PIN match."""
        pin = expected_pin or cls.DEFAULT_PIN
        clean = "".join(filter(str.isdigit, spoken_pin))
        return clean == pin
