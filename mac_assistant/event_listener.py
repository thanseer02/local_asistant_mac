"""macOS low-level kernel notification listener using libSystem notify(3)."""

import ctypes
import logging
from typing import Dict, List

logger = logging.getLogger("MacAssistant.Events")

# Comprehensive macOS kernel notification events
# Covering modern Sonoma / Sequoia screensaver dismissals, display power states, and lock/unlock
NOTIFICATION_EVENTS: List[bytes] = [
    # Screensaver states
    b'com.apple.screensaver.didstop',
    b'com.apple.screensaver.willstop',
    b'com.apple.screensaver.didquit',
    b'com.apple.screensaver.stopped',

    # Lock and unlock states
    b'com.apple.screenIsUnlocked',
    b'com.apple.sessionDidUnlock',
    b'com.apple.system.loginwindow.sessionDidUnlock',
    b'com.apple.sessionDidBecomeActive',
    b'com.apple.system.loginwindow.sessionDidBecomeActive',
]


class NotificationListener:
    """Manages kernel event subscriptions for lock, unlock, and screensaver states."""

    def __init__(self):
        self._lib = ctypes.cdll.LoadLibrary('/usr/lib/libSystem.B.dylib')
        self.fd_map: Dict[int, str] = {}
        self._tokens: List[ctypes.c_int] = []

    def register(self) -> bool:
        """Subscribes file descriptors to macOS kernel notification events."""
        for event in NOTIFICATION_EVENTS:
            fd = ctypes.c_int()
            token = ctypes.c_int()
            status = self._lib.notify_register_file_descriptor(
                event, ctypes.byref(fd), 0, ctypes.byref(token)
            )
            if status == 0 and fd.value >= 0:
                self.fd_map[fd.value] = event.decode('utf-8')
                self._tokens.append(token)
                logger.info("Registered kernel listener for: %s", event.decode('utf-8'))
            else:
                logger.warning("Failed to register %s (status %d)", event.decode('utf-8'), status)

        return bool(self.fd_map)

    def get_descriptors(self) -> List[int]:
        """Returns list of active file descriptors to pass to select()."""
        return list(self.fd_map.keys())
