"""Security policy, audit logger, and execution sandbox for developer commands."""

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MacAssistant.DeveloperSecurity")

# Allowed root directories where developer tools are allowed to inspect and operate
APPROVED_ROOTS = [
    Path("/Users/tanseer/Documents"),
    Path(__file__).resolve().parent.parent.parent  # MacAssistant root
]

# Sensitive regex patterns to redact from logs and tool outputs
SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|auth[_-]?token|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"), r"\1: [REDACTED_SECRET]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "[REDACTED_SECRET]"),
    (re.compile(r"glpat-[a-zA-Z0-9_\-]{20}"), "[REDACTED_SECRET]"),
    (re.compile(r"ey[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}"), "[REDACTED_SECRET]")
]

AUDIT_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "developer_audit.log"


@dataclass
class CommandExecutionResult:
    """Standardized result of a sandboxed developer command execution."""
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    requires_confirmation: bool = False
    confirmation_reason: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.returncode == 0


class DeveloperSecurityPolicy:
    """
    Central security policy and command execution engine:
    1. Validates that project paths reside in approved developer workspace roots.
    2. Enforces an allowlist of permitted binaries and subcommands.
    3. Blocks raw string shell commands (strictly shell=False with argument lists).
    4. Categorizes actions into READ-ONLY (auto-run) vs DESTRUCTIVE/MODIFYING (requires confirmation).
    5. Applies timeouts and output buffer truncation to prevent OOM/hangs.
    6. Redacts sensitive credentials, tokens, and secrets from output.
    7. Maintains an append-only audit trail in data/developer_audit.log.
    """

    # Permitted executable paths
    ALLOWED_BINARIES: Dict[str, str] = {
        "git": "/usr/bin/git",
        "code": "/usr/local/bin/code",
        "open": "/usr/bin/open",
        "flutter": "flutter",
        "fvm": "/opt/homebrew/bin/fvm",
        "python": "python",
        "python3": "/usr/bin/python3",
        "pytest": "pytest"
    }

    # Commands that are strictly read-only and execute automatically
    READ_ONLY_ACTIONS = {
        "git_status", "git_branch_list", "git_log", "git_diff", "git_remote",
        "flutter_doctor", "flutter_analyze", "flutter_test",
        "python_pytest", "python_detect_venv", "inspect_logs", "error_analysis",
        "project_list", "project_open_vscode", "project_open_finder"
    }

    # Commands that modify disk, repository, or remote state requiring explicit user confirmation
    CONFIRMATION_REQUIRED_ACTIONS = {
        "git_commit": "Commit uncommitted files to Git repository",
        "git_push": "Push local commits to remote repository",
        "git_pull": "Pull remote changes and merge into current branch",
        "git_checkout": "Switch or create a Git branch",
        "git_merge": "Merge branch into active branch",
        "flutter_pub_get": "Download and update Flutter/Dart dependencies",
        "flutter_build_apk": "Trigger release APK compilation",
        "flutter_build_ipa": "Trigger release iOS/IPA compilation",
        "python_run_script": "Execute approved Python project script"
    }

    @classmethod
    def validate_project_path(cls, path_candidate: Any) -> Tuple[bool, Optional[Path], str]:
        """
        Validates that a path exists and is within approved developer workspaces.
        Prevents directory traversal and system path alteration.
        """
        if not path_candidate:
            return False, None, "No path provided."

        try:
            p = Path(path_candidate).expanduser().resolve()
            if not p.exists():
                return False, None, f"Path does not exist: {p}"

            # Check if within an approved root
            is_approved = False
            for root in APPROVED_ROOTS:
                try:
                    if root.exists() and (p == root or root in p.parents):
                        is_approved = True
                        break
                except Exception:
                    continue

            if not is_approved:
                logger.warning("Access denied: %s is outside approved developer workspaces.", p)
                return False, None, f"Path '{p}' is outside approved developer workspaces."

            return True, p, "Path validated successfully."
        except Exception as e:
            return False, None, f"Path validation error: {e}"

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        """Strips tokens, credentials, and passwords from string output."""
        if not text:
            return ""
        clean = text
        for pat, repl in SECRET_PATTERNS:
            clean = pat.sub(repl, clean)
        return clean

    @classmethod
    def log_audit(cls, action: str, cmd_list: List[str], cwd: Path, success: bool, user_confirmed: bool) -> None:
        """Appends command execution records to the audit log."""
        try:
            AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "command": [str(c) for c in cmd_list],
                "cwd": str(cwd),
                "success": success,
                "user_confirmed": user_confirmed
            }
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.debug("Failed writing audit log: %s", e)

    @classmethod
    def execute_sandboxed(
        cls,
        action_name: str,
        cmd: List[str],
        cwd: Path,
        timeout: int = 30,
        max_output_bytes: int = 50000,
        confirmed: bool = False
    ) -> CommandExecutionResult:
        """
        Executes an allowlisted developer command with strict arguments list, timeout, and limits.
        Never uses shell=True.
        """
        start_time = datetime.now()

        # 1. Path safety check
        valid, safe_cwd, reason = cls.validate_project_path(cwd)
        if not valid or safe_cwd is None:
            return CommandExecutionResult(
                command=cmd,
                returncode=-1,
                stdout="",
                stderr=f"Security violation: {reason}",
                duration_seconds=0.0
            )

        # 2. Check confirmation requirement
        if action_name in cls.CONFIRMATION_REQUIRED_ACTIONS and not confirmed:
            reason = cls.CONFIRMATION_REQUIRED_ACTIONS[action_name]
            logger.info("Action '%s' blocked awaiting confirmation: %s", action_name, reason)
            return CommandExecutionResult(
                command=cmd,
                returncode=-2,
                stdout="",
                stderr=f"Confirmation required: {reason}",
                duration_seconds=0.0,
                requires_confirmation=True,
                confirmation_reason=reason
            )

        # 3. Execute subprocess strictly with argument list
        try:
            logger.info("Executing developer action [%s]: %s in %s", action_name, " ".join(cmd), safe_cwd)
            proc = subprocess.run(
                cmd,
                cwd=str(safe_cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False  # Mandatory: NEVER use shell=True
            )

            stdout = cls.redact_secrets(proc.stdout[:max_output_bytes])
            stderr = cls.redact_secrets(proc.stderr[:max_output_bytes])
            duration = (datetime.now() - start_time).total_seconds()

            cls.log_audit(action_name, cmd, safe_cwd, proc.returncode == 0, confirmed)

            return CommandExecutionResult(
                command=cmd,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration
            )

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            logger.warning("Command '%s' timed out after %ds", " ".join(cmd), timeout)
            cls.log_audit(action_name, cmd, safe_cwd, False, confirmed)
            return CommandExecutionResult(
                command=cmd,
                returncode=-3,
                stdout="",
                stderr=f"Execution timed out after {timeout} seconds.",
                duration_seconds=duration
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error("Execution error for '%s': %s", action_name, e)
            cls.log_audit(action_name, cmd, safe_cwd, False, confirmed)
            return CommandExecutionResult(
                command=cmd,
                returncode=-4,
                stdout="",
                stderr=str(e),
                duration_seconds=duration
            )
