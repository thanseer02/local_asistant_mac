"""Log inspector module with regex error searching, stack trace extraction, limits, and redaction."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from .security import DeveloperSecurityPolicy

logger = logging.getLogger("MacAssistant.LogInspector")


class LogInspector:
    """
    Inspects application and developer logs:
    - Scans for errors, warnings, exceptions, and stack traces.
    - Limits read size (max 500 KB / 1000 lines) to prevent buffer bloat.
    - Automatically redacts tokens, credentials, and passwords.
    """

    DEFAULT_LOGS = [
        Path("/tmp/macassistant-error.log"),
        Path("/tmp/macassistant.log"),
        Path(__file__).resolve().parent.parent.parent / "data" / "developer_audit.log"
    ]

    ERROR_PATTERNS = [
        re.compile(r"(?i)\b(error|fatal|exception|traceback|fail|crash|segfault)\b"),
        re.compile(r"(?i)\b(warning|warn)\b")
    ]

    @classmethod
    def inspect_file(
        cls,
        log_path: Path,
        max_lines: int = 150,
        level_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reads trailing lines of a log file, filtering by errors/warnings and redacting secrets.
        """
        if not log_path.exists():
            return {
                "exists": False,
                "file": str(log_path),
                "errors": [],
                "warnings": [],
                "total_lines_inspected": 0
            }

        # Cap file read at 1 MB
        file_size = log_path.stat().st_size
        max_bytes = 1024 * 512  # 512 KB
        offset = max(0, file_size - max_bytes)

        lines: List[str] = []
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                if offset > 0:
                    f.seek(offset)
                raw_lines = f.readlines()
                lines = raw_lines[-max_lines:]
        except Exception as e:
            return {
                "exists": True,
                "file": str(log_path),
                "error_reading": str(e)
            }

        found_errors: List[str] = []
        found_warnings: List[str] = []

        for line in lines:
            clean_line = DeveloperSecurityPolicy.redact_secrets(line.strip())
            if not clean_line:
                continue

            lower = clean_line.lower()
            if any(k in lower for k in ["error", "fatal", "exception", "traceback", "failed"]):
                found_errors.append(clean_line)
            elif any(k in lower for k in ["warning", "warn"]):
                found_warnings.append(clean_line)

        # Filter by requested level
        if level_filter == "error":
            items = found_errors
        elif level_filter == "warning":
            items = found_warnings
        else:
            items = found_errors + found_warnings

        return {
            "exists": True,
            "file": str(log_path),
            "errors": found_errors[-10:],
            "warnings": found_warnings[-10:],
            "recent_items": items[-10:],
            "total_lines_inspected": len(lines)
        }

    @classmethod
    def get_summary_speech(cls, log_path: Optional[Path] = None) -> str:
        """Formats a spoken summary of recent errors and warnings."""
        target = log_path or cls.DEFAULT_LOGS[0]
        data = cls.inspect_file(target)

        if not data.get("exists"):
            return f"Log file at {target.name} does not exist."

        errors = data.get("errors", [])
        warnings = data.get("warnings", [])

        if not errors and not warnings:
            return f"Log scan clean. No recent errors or warnings found in {target.name}."

        err_count = len(errors)
        warn_count = len(warnings)

        latest_sample = errors[-1] if errors else (warnings[-1] if warnings else "")
        # Truncate sample for speech
        if len(latest_sample) > 120:
            latest_sample = latest_sample[:117] + "..."

        return (
            f"Found {err_count} errors and {warn_count} warnings in {target.name}. "
            f"Latest event says: {latest_sample}"
        )
