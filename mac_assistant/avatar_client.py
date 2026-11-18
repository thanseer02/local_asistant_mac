"""Client helper to send events to the avatar overlay process via Unix domain socket."""

import json
import logging
import socket
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.AvatarClient")
SOCKET_PATH = "/tmp/macassistant_avatar.sock"


class AvatarClient:
    """Thread-safe IPC client communicating with the AvatarOverlay subprocess."""

    @staticmethod
    def send_event(action: str, extra: Optional[Dict[str, Any]] = None, timeout: float = 0.2) -> bool:
        """Sends command event to avatar overlay socket without blocking the caller."""
        payload = {"action": action}
        if extra:
            payload.update(extra)

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(timeout)
                client.connect(SOCKET_PATH)
                msg = json.dumps(payload) + "\n"
                client.sendall(msg.encode("utf-8"))
            return True
        except (FileNotFoundError, ConnectionRefusedError):
            # Overlay process is either disabled or starting up; non-fatal
            return False
        except Exception as e:
            logger.debug("Failed sending avatar event '%s': %s", action, e)
            return False

    @classmethod
    def speaking_start(cls) -> bool:
        """Signals speech playback has begun."""
        return cls.send_event("speaking_start")

    @classmethod
    def speaking_end(cls) -> bool:
        """Signals speech playback has completed."""
        return cls.send_event("speaking_end")

    @classmethod
    def thinking(cls) -> bool:
        """Signals LLM or intelligence inference is in progress."""
        return cls.send_event("thinking")

    @classmethod
    def hide(cls) -> bool:
        """Forces avatar to conceal immediately."""
        return cls.send_event("hide")

    @classmethod
    def update_config(cls, config: Dict[str, Any]) -> bool:
        """Sends new avatar config parameters across IPC."""
        return cls.send_event("config_update", {"config": config})
