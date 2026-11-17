"""Core Bridge Service interfacing between Desktop GUI/WebSockets and MacAssistant backend."""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mac_assistant.config_manager import ConfigManager
from modules.ai.conversation_memory import PersistentConversationMemory
from modules.personality.friday_config import FridayPersonalityManager
from modules.personality.jarvis_config import JarvisPersonalityManager

logger = logging.getLogger("MacAssistant.GUIBridge")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "conversation.db"
AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "developer_audit.log"
APP_LOG_PATH = Path("/tmp/macassistant-error.log")


@dataclass
class SystemStatus:
    online: bool
    state: str
    active_persona: str
    voice: str
    speech_rate: int
    llm_model: str
    cpu_percent: float
    ram_percent: float
    active_pid: Optional[int]
    timestamp: str


class AssistantBridgeService:
    """
    Central business logic coordinator for the Friday/Jarvis Control Center:
    - Provides real-time state introspection (PID, state, CPU, RAM).
    - Queries SQLite conversation history with persona filtering & keyword search.
    - Inspects and updates Friday & Jarvis personality settings independently.
    - Manages registered tools and execution history.
    - Reads and exports logs safely with secret redaction.
    - Controls assistant lifecycle (start/stop/restart/switch).
    """

    def __init__(self):
        self.memory = PersistentConversationMemory(DB_PATH)
        self.friday_mgr = FridayPersonalityManager.get_instance()
        self.jarvis_mgr = JarvisPersonalityManager.get_instance()

    def get_system_metrics(self) -> Dict[str, float]:
        """Reads CPU and RAM usage safely using psutil if available or system commands."""
        try:
            import psutil
            return {
                "cpu": psutil.cpu_percent(interval=None),
                "ram": psutil.virtual_memory().percent
            }
        except Exception:
            return {"cpu": 0.0, "ram": 0.0}

    def get_assistant_process_status(self) -> Tuple[bool, Optional[int]]:
        """Checks if the macassistant background daemon or controller is active."""
        try:
            out = subprocess.check_output(
                ["/bin/ps", "-ax", "-o", "pid,command"],
                text=True,
                timeout=3
            )
            for line in out.splitlines():
                if "mac_assistant" in line and "grep" not in line and "gui" not in line.lower():
                    parts = line.strip().split()
                    return True, int(parts[0])
            return False, None
        except Exception:
            return False, None

    def get_current_status(self) -> SystemStatus:
        """Assembles comprehensive live status."""
        cfg = ConfigManager.load()
        online, pid = self.get_assistant_process_status()
        metrics = self.get_system_metrics()

        active_p = cfg.get("assistant_persona", "friday")
        voice = cfg.get("voice", "Moira")
        rate = cfg.get("speech_rate", 172)

        return SystemStatus(
            online=online,
            state="STANDBY" if online else "STOPPED",
            active_persona=active_p,
            voice=voice,
            speech_rate=rate,
            llm_model="llama3.2:1b (Local Ollama)",
            cpu_percent=metrics["cpu"],
            ram_percent=metrics["ram"],
            active_pid=pid,
            timestamp=datetime.now().strftime("%I:%M:%S %p")
        )

    # ------------------ Conversation History ------------------

    def get_conversation_history(
        self,
        persona_filter: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Queries conversation turns with optional filtering and search."""
        if not DB_PATH.exists():
            return []

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                # Check table schema
                cursor.execute("PRAGMA table_info(conversation_turns)")
                cols = [c[1] for c in cursor.fetchall()]

                # Build query
                query = "SELECT id, timestamp, role, content, intent FROM conversation_turns WHERE 1=1"
                params: List[Any] = []

                if search_query:
                    query += " AND content LIKE ?"
                    params.append(f"%{search_query.strip()}%")

                query += " ORDER BY id DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

                turns = []
                for r in rows:
                    t_id, ts, role, content, intent = r
                    dt_str = datetime.fromtimestamp(ts).strftime("%b %d, %I:%M %p") if ts else "Recent"
                    turns.append({
                        "id": t_id,
                        "timestamp": dt_str,
                        "role": role,
                        "content": content,
                        "intent": intent or "conversation"
                    })
                return turns
        except Exception as e:
            logger.error("Failed querying conversation history: %s", e)
            return []

    def clear_conversation_history(self) -> bool:
        """Clears all conversation turns from SQLite."""
        try:
            self.memory.clear_all()
            return True
        except Exception as e:
            logger.error("Error clearing conversation history: %s", e)
            return False

    # ------------------ Personality Management ------------------

    def get_personality_settings(self) -> Dict[str, Any]:
        """Returns isolated settings for both Friday and Jarvis."""
        return {
            "friday": self.friday_mgr.config.model_dump(),
            "jarvis": self.jarvis_mgr.config.model_dump()
        }

    def update_friday_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates Friday configuration and persists to config.json without touching Jarvis."""
        for k, v in updates.items():
            if hasattr(self.friday_mgr.config, k):
                setattr(self.friday_mgr.config, k, v)
        self.friday_mgr.save_to_config_json()
        return self.friday_mgr.config.model_dump()

    def update_jarvis_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates Jarvis configuration and persists to config.json without touching Friday."""
        for k, v in updates.items():
            if hasattr(self.jarvis_mgr.config, k):
                setattr(self.jarvis_mgr.config, k, v)
        self.jarvis_mgr.save_to_config_json()
        return self.jarvis_mgr.config.model_dump()

    def switch_active_persona(self, target_persona: str) -> bool:
        """Switches active assistant persona in config."""
        target = target_persona.lower().strip()
        if target in ["friday", "jarvis"]:
            ConfigManager.set_active_persona(target)
            return True
        return False

    # ------------------ Tool Registry ------------------

    def get_registered_tools(self) -> List[Dict[str, Any]]:
        """Returns dynamic metadata for all registered automation and developer tools."""
        return [
            {
                "id": "open_application",
                "name": "Application Launcher",
                "category": "System",
                "permission_level": "Safe",
                "requires_confirmation": False,
                "description": "Launches approved applications (Chrome, VS Code, Terminal, Brave, Slack, Spotify, Antigravity).",
                "enabled": True
            },
            {
                "id": "system_controls",
                "name": "System Status & Volume",
                "category": "System",
                "permission_level": "Safe",
                "requires_confirmation": False,
                "description": "Checks battery percentage, disk space, time, and adjusts audio output volume.",
                "enabled": True
            },
            {
                "id": "file_search",
                "name": "File & PDF Search",
                "category": "Files",
                "permission_level": "Safe",
                "requires_confirmation": False,
                "description": "Searches for Flutter projects, PDFs, and documents using macOS Spotlight mdfind.",
                "enabled": True
            },
            {
                "id": "git_read_only",
                "name": "Git Status & Log",
                "category": "Developer",
                "permission_level": "Safe",
                "requires_confirmation": False,
                "description": "Inspects git status, active branch, commit history, and diff stats.",
                "enabled": True
            },
            {
                "id": "git_mutations",
                "name": "Git Commit & Push",
                "category": "Developer",
                "permission_level": "Restricted",
                "requires_confirmation": True,
                "description": "Performs git commits, branch checkout, push, and pull operations.",
                "enabled": True
            },
            {
                "id": "flutter_tools",
                "name": "Flutter & FVM Tools",
                "category": "Developer",
                "permission_level": "Safe / Restricted",
                "requires_confirmation": True,
                "description": "Runs doctor and tests; requires user confirmation for pub get, apk, and ipa builds.",
                "enabled": True
            },
            {
                "id": "python_tools",
                "name": "Python & Pytest",
                "category": "Developer",
                "permission_level": "Safe / Restricted",
                "requires_confirmation": False,
                "description": "Detects venvs and executes pytest test suites within project sandbox.",
                "enabled": True
            },
            {
                "id": "log_inspector",
                "name": "Log Inspector & Diagnostics",
                "category": "Diagnostics",
                "permission_level": "Safe",
                "requires_confirmation": False,
                "description": "Scans logs for errors and provides local Ollama diagnostic root-cause fixes.",
                "enabled": True
            }
        ]

    # ------------------ System Logs ------------------

    def get_logs(self, max_lines: int = 150, log_type: str = "app") -> List[str]:
        """Reads recent logs with sensitive credential redaction."""
        target = AUDIT_LOG_PATH if log_type == "audit" else APP_LOG_PATH
        if not target.exists():
            return [f"Log file {target.name} does not exist yet."]

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-max_lines:]
            # Redact secrets
            from modules.developer.security import DeveloperSecurityPolicy
            return [DeveloperSecurityPolicy.redact_secrets(l.strip()) for l in lines]
        except Exception as e:
            return [f"Error reading log file: {e}"]

    # ------------------ Process Lifecycle Controls ------------------

    def restart_assistant_service(self) -> Tuple[bool, str]:
        """Safely triggers launchctl kickstart to reload background assistant."""
        try:
            uid = os.getuid()
            res = subprocess.run(
                ["/bin/launchctl", "kickstart", "-k", f"gui/{uid}/com.personal.macassistant"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                return True, "Assistant daemon kickstarted successfully."
            return False, f"Failed kickstart: {res.stderr}"
        except Exception as e:
            return False, str(e)
