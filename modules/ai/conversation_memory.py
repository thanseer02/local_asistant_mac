"""Persistent SQLite conversation memory for multi-turn session storage."""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.SQLiteMemory")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "conversation.db"


class PersistentConversationMemory:
    """
    SQLite-backed conversation memory storing turns with timestamps and intent tags.
    Maintains clean session isolation, user clearing, and retrieval of recent context.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    role TEXT,
                    content TEXT,
                    intent TEXT
                )
            """)
            conn.commit()

    def record_turn(self, role: str, content: str, intent: str = "conversation") -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO conversation_turns (timestamp, role, content, intent) VALUES (?, ?, ?, ?)",
                    (time.time(), role, content.strip(), intent)
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed recording turn to SQLite: %s", e)

    def get_recent_turns(self, limit: int = 10) -> List[Dict[str, str]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT role, content FROM conversation_turns ORDER BY id DESC LIMIT ?",
                    (limit * 2,)
                )
                rows = cursor.fetchall()
                # Return in chronological order
                return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
        except Exception as e:
            logger.error("Failed reading turns from SQLite: %s", e)
            return []

    def recall_last_discussion(self) -> Optional[str]:
        """Summarizes or returns the last topic discussed."""
        turns = self.get_recent_turns(limit=3)
        if not turns:
            return None
        last_user = next((t["content"] for t in reversed(turns) if t["role"] == "user"), None)
        last_bot = next((t["content"] for t in reversed(turns) if t["role"] == "assistant"), None)
        if last_user:
            return f"We were just discussing: '{last_user}'. My reply was: '{last_bot}'."
        return None

    def clear_all(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM conversation_turns")
                conn.commit()
            logger.info("Persistent conversation memory cleared.")
        except Exception as e:
            logger.error("Failed clearing SQLite memory: %s", e)
