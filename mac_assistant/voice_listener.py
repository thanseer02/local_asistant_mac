"""Voice wake-word listener safely disabled to prevent mic feedback loops."""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("MacAssistant.VoiceListener")


class VoiceListener:
    """Safe listener placeholder preventing audio loop triggers."""

    def __init__(self, on_wake_callback: Optional[Callable[[], None]] = None, on_command_callback: Optional[Callable[[str], None]] = None):
        self.running = False

    def start(self, config: Dict[str, Any]) -> None:
        logger.info("Voice wake listener safely disarmed.")

    def stop(self) -> None:
        self.running = False
