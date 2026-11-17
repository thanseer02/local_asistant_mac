"""Conversation session state and context management."""

import time
from typing import Any, Dict, List


class ConversationManager:
    """Maintains local conversation memory, message history, and session metadata."""

    def __init__(self, max_history: int = 30):
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []
        self.session_start_time = time.time()
        self.last_user_utterance: str = ""
        self.last_assistant_response: str = ""

    def record_user_message(self, text: str) -> None:
        """Stores user utterance in session memory."""
        self.last_user_utterance = text
        self.history.append({"role": "user", "content": text, "timestamp": time.time()})
        self._trim()

    def record_assistant_message(self, text: str) -> None:
        """Stores assistant reply in session memory."""
        self.last_assistant_response = text
        self.history.append({"role": "assistant", "content": text, "timestamp": time.time()})
        self._trim()

    def _trim(self) -> None:
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
