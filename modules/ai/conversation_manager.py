"""Unified conversation manager coordinating session memory, SQLite, and context building."""

import logging
from typing import Any, Dict, List, Optional
from modules.ai.conversation_memory import PersistentConversationMemory
from modules.personality.personality_config import PersonalityManager

logger = logging.getLogger("MacAssistant.ConversationManager")


class ConversationManager:
    """Coordinates active in-memory turns with optional persistent SQLite storage."""

    def __init__(self, use_sqlite: bool = True):
        self.personality_mgr = PersonalityManager.get_instance()
        self.sqlite_memory = PersistentConversationMemory() if use_sqlite else None
        self.session_turns: List[Dict[str, str]] = []

    def record_user_turn(self, utterance: str, intent: str = "conversation") -> None:
        self.session_turns.append({"role": "user", "content": utterance})
        if self.sqlite_memory and self.personality_mgr.config.persist_memory_sqlite:
            self.sqlite_memory.record_turn("user", utterance, intent=intent)

    def record_assistant_turn(self, response: str, intent: str = "conversation") -> None:
        self.session_turns.append({"role": "assistant", "content": response})
        if self.sqlite_memory and self.personality_mgr.config.persist_memory_sqlite:
            self.sqlite_memory.record_turn("assistant", response, intent=intent)

    def get_messages_for_llm(self, system_prompt: str) -> List[Dict[str, str]]:
        max_turns = self.personality_mgr.config.max_history_turns * 2
        history = self.session_turns[-max_turns:]
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        return messages

    def clear(self) -> None:
        self.session_turns.clear()
        if self.sqlite_memory:
            self.sqlite_memory.clear_all()
        logger.info("Session history and persistent memory cleared.")
