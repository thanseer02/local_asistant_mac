"""Local multi-turn conversation memory with persistence and context pruning."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.ConversationMemory")

DEFAULT_MEMORY_FILE = Path(__file__).resolve().parent.parent / "conversation_history.json"


class ConversationMemory:
    """
    Maintains active multi-turn conversation history for local Ollama.
    Allows local persistence, history limit enforcement, and explicit clearing.
    """

    def __init__(
        self,
        max_turns: int = 12,
        persist: bool = True,
        storage_path: Optional[Path] = None
    ):
        self.max_turns = max_turns
        self.persist = persist
        self.storage_path = storage_path or DEFAULT_MEMORY_FILE
        self.history: List[Dict[str, str]] = []
        self._load()

    def add_user_message(self, message: str) -> None:
        """Appends user message to history."""
        self.history.append({"role": "user", "content": message.strip()})
        self._prune_and_save()

    def add_assistant_message(self, message: str) -> None:
        """Appends assistant response to history."""
        self.history.append({"role": "assistant", "content": message.strip()})
        self._prune_and_save()

    def get_context_messages(self, system_prompt: str) -> List[Dict[str, str]]:
        """Returns message list formatted for Ollama /api/chat with system prompt."""
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(self.history)
        return msgs

    def clear(self) -> None:
        """Clears memory history."""
        self.history.clear()
        if self.persist and self.storage_path.exists():
            try:
                self.storage_path.unlink()
            except Exception:
                pass
        logger.info("Conversation memory cleared.")

    def _prune_and_save(self) -> None:
        """Enforces max_turns and writes to disk if persistence is enabled."""
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2):]

        if self.persist:
            try:
                with open(self.storage_path, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception as e:
                logger.debug("Failed saving conversation memory: %s", e)

    def _load(self) -> None:
        """Loads existing memory if file exists."""
        if self.persist and self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.debug("Loaded %d messages from memory store.", len(self.history))
            except Exception:
                self.history = []
