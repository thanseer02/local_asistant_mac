"""Client helper to send events to the VRM avatar overlay process via Unix domain socket."""

import json
import logging
import socket
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.AvatarClient")
SOCKET_PATH = "/tmp/macassistant_avatar.sock"


class AvatarClient:
    """Thread-safe IPC client communicating with the VRM Avatar & Message Overlay subprocess."""

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
    def speaking_start(cls, message: str = "", persona: str = "Assistant") -> bool:
        """Signals speech playback has begun, passing message text to show in the popup bubble."""
        return cls.send_event("speaking_start", {"message": message, "persona": persona})

    @classmethod
    def speaking_end(cls) -> bool:
        """Signals speech playback has completed."""
        return cls.send_event("speaking_end")

    @classmethod
    def thinking(cls) -> bool:
        """Signals LLM or intelligence inference is in progress."""
        return cls.send_event("thinking")

    @classmethod
    def listening(cls) -> bool:
        """Signals wake word detection and speech recognition is listening."""
        return cls.send_event("listening")

    @classmethod
    def notification(cls) -> bool:
        """Signals an alert, reminder, or notification has arrived."""
        return cls.send_event("notification")

    @classmethod
    def error(cls) -> bool:
        """Signals an error or unrecognized command."""
        return cls.send_event("error")

    @classmethod
    def sleeping(cls) -> bool:
        """Transitions avatar to low-power sleeping state."""
        return cls.send_event("sleeping")

    @classmethod
    def idle(cls) -> bool:
        """Transitions avatar back to normal idle state."""
        return cls.send_event("idle")

    @classmethod
    def amplitude(cls, amp: float, vowel: str = "aa") -> bool:
        """Sends audio amplitude loudness and target vowel for blendshape lip-sync."""
        return cls.send_event("amplitude", {"amplitude": amp, "vowel": vowel})

    @classmethod
    def expression(cls, exp: str, weight: float = 1.0) -> bool:
        """Sets avatar facial expression (e.g. happy, surprised, neutral, sad)."""
        return cls.send_event("expression", {"expression": exp, "weight": weight})

    @classmethod
    def show_message(cls, text: str, sender: str = "Assistant") -> bool:
        """Enqueues popup message bubble without triggering speaking state."""
        return cls.send_event("message", {"text": text, "sender": sender})

    @classmethod
    def set_visibility(cls, visible: bool) -> bool:
        """Controls avatar window visibility."""
        return cls.send_event("visibility", {"visible": visible})

    @classmethod
    def set_position(cls, position: str) -> bool:
        """Sets avatar position to corner (bottom-right, bottom-left, top-right, top-left)."""
        return cls.send_event("position", {"position": position})

    @classmethod
    def hide(cls) -> bool:
        """Conceals avatar overlay."""
        return cls.set_visibility(False)

    @classmethod
    def show(cls) -> bool:
        """Shows avatar overlay."""
        return cls.set_visibility(True)

    @classmethod
    def update_config(cls, config: Dict[str, Any]) -> bool:
        """Sends new avatar config parameters across IPC."""
        return cls.send_event("config_update", {"config": config})
