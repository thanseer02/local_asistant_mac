"""Persistent SQLite conversation memory for multi-turn session storage and user facts/notes."""

import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.SQLiteMemory")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "conversation.db"


class PersistentConversationMemory:
    """SQLite-backed conversation memory storing turns with timestamps and user facts/notes."""

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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    key TEXT UNIQUE,
                    fact TEXT
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
                return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
        except Exception as e:
            logger.error("Failed reading turns from SQLite: %s", e)
            return []

    def remember_fact(self, key: str, fact: str) -> None:
        """Stores a persistent fact or note (e.g., 'remember that my doctor appointment is on Friday')."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO user_facts (timestamp, key, fact) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET timestamp=excluded.timestamp, fact=excluded.fact",
                    (time.time(), key.strip().lower(), fact.strip())
                )
                conn.commit()
            logger.info("Saved user fact [%s]: %s", key, fact)
        except Exception as e:
            logger.error("Failed remembering fact: %s", e)

    def recall_fact(self, query: str) -> Optional[str]:
        """Recalls a stored fact matching keyword query."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, fact FROM user_facts ORDER BY timestamp DESC")
                rows = cursor.fetchall()
                for key, fact in rows:
                    if key in query.lower() or any(w in fact.lower() for w in query.lower().split() if len(w) > 3):
                        return fact
        except Exception as e:
            logger.error("Failed recalling fact: %s", e)
        return None

    def get_all_facts(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, fact, timestamp FROM user_facts ORDER BY timestamp DESC")
                return [{"key": r[0], "fact": r[1], "timestamp": r[2]} for r in cursor.fetchall()]
        except Exception:
            return []

    def recall_last_discussion(self) -> Optional[str]:
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
                cursor.execute("DELETE FROM user_facts")
                conn.commit()
            logger.info("Persistent conversation memory and facts cleared.")
        except Exception as e:
            logger.error("Failed clearing SQLite memory: %s", e)
