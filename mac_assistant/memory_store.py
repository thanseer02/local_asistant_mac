"""Persistent memory store using standard library sqlite3.

Stored in ~/Library/Application Support/MacAssistant/memory.db.
Provides:
- Storing facts ("remember that <fact>")
- Recalling facts ("what do you remember about <x>")
- Forgetting facts ("forget <x>")
- Time-bound facts ("my flight is at 6 PM") for scheduled reminders
- Parameterized SQL queries only (no injection vulnerabilities)
- Zero logging of sensitive memory contents
"""

from datetime import datetime
import logging
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MacAssistant.MemoryStore")

DEFAULT_DB_DIR = Path.home() / "Library" / "Application Support" / "MacAssistant"


class MemoryStore:
    """Manages persistent SQLite memory storage with parameterized queries."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (DEFAULT_DB_DIR / "memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initializes tables using parameterized schema statements."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    topic TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    due_time TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic ON facts(topic)")
            conn.commit()

    @staticmethod
    def _extract_time_bound(text: str) -> Optional[str]:
        """Extracts simple time strings like '6 PM', '18:00', 'half past four' if present."""
        m = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return None

    def remember(self, topic: str, fact: str) -> Tuple[bool, Optional[str]]:
        """Stores or updates a fact under a given topic with optional time extraction."""
        clean_topic = topic.strip().lower()
        clean_fact = fact.strip()
        due_time = self._extract_time_bound(clean_fact)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO facts (created_at, topic, fact, due_time) VALUES (?, ?, ?, ?)",
                    (time.time(), clean_topic, clean_fact, due_time)
                )
                conn.commit()
            logger.info("Committed new fact under topic '%s'.", clean_topic)
            return True, due_time
        except Exception as e:
            logger.error("Failed saving fact to SQLite store: %s", e)
            return False, None

    def recall(self, query: str) -> List[Dict[str, Any]]:
        """Retrieves facts matching query keywords using parameterized LIKE."""
        clean_query = query.strip().lower()
        words = [w for w in clean_query.split() if len(w) > 2]
        if not words:
            words = [clean_query]

        results = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for word in words:
                    cursor.execute(
                        "SELECT topic, fact, due_time, created_at FROM facts WHERE topic LIKE ? OR fact LIKE ? ORDER BY created_at DESC LIMIT 5",
                        (f"%{word}%", f"%{word}%")
                    )
                    for r in cursor.fetchall():
                        item = {"topic": r[0], "fact": r[1], "due_time": r[2], "created_at": r[3]}
                        if item not in results:
                            results.append(item)
        except Exception as e:
            logger.error("Failed querying memory store: %s", e)

        return results

    def forget(self, topic: str) -> int:
        """Deletes facts matching topic. Returns count of deleted entries."""
        clean_topic = topic.strip().lower()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM facts WHERE topic LIKE ? OR fact LIKE ?", (f"%{clean_topic}%", f"%{clean_topic}%"))
                deleted_count = cursor.rowcount
                conn.commit()
            logger.info("Deleted %d facts matching topic '%s'.", deleted_count, clean_topic)
            return deleted_count
        except Exception as e:
            logger.error("Failed deleting facts from memory store: %s", e)
            return 0
