"""Git manager module handling read-only queries and confirmation-gated mutations."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .security import DeveloperSecurityPolicy, CommandExecutionResult

logger = logging.getLogger("MacAssistant.GitManager")


class GitManager:
    """
    Manages Git operations with strict privilege separation:
    - Read-Only (Immediate): status, branch list, log, diff, remotes.
    - Modifying/Destructive (Confirmation Required): commit, push, pull, checkout, merge.
    """

    GIT_BIN = DeveloperSecurityPolicy.ALLOWED_BINARIES["git"]

    @classmethod
    def get_status(cls, repo_path: Path) -> CommandExecutionResult:
        """Retrieves repository status (read-only)."""
        cmd = [cls.GIT_BIN, "status", "--short", "--branch"]
        return DeveloperSecurityPolicy.execute_sandboxed("git_status", cmd, cwd=repo_path)

    @classmethod
    def get_active_branch(cls, repo_path: Path) -> CommandExecutionResult:
        """Retrieves the active branch name (read-only)."""
        cmd = [cls.GIT_BIN, "rev-parse", "--abbrev-ref", "HEAD"]
        return DeveloperSecurityPolicy.execute_sandboxed("git_branch_list", cmd, cwd=repo_path)

    @classmethod
    def get_log(cls, repo_path: Path, max_count: int = 5) -> CommandExecutionResult:
        """Retrieves recent commit log entries (read-only)."""
        cmd = [cls.GIT_BIN, "log", f"-n{max_count}", "--oneline", "--decorate"]
        return DeveloperSecurityPolicy.execute_sandboxed("git_log", cmd, cwd=repo_path)

    @classmethod
    def get_diff(cls, repo_path: Path, stat_only: bool = True) -> CommandExecutionResult:
        """Retrieves working directory diff summary (read-only)."""
        cmd = [cls.GIT_BIN, "diff", "--stat"] if stat_only else [cls.GIT_BIN, "diff"]
        return DeveloperSecurityPolicy.execute_sandboxed("git_diff", cmd, cwd=repo_path)

    @classmethod
    def get_remotes(cls, repo_path: Path) -> CommandExecutionResult:
        """Lists configured Git remotes (read-only)."""
        cmd = [cls.GIT_BIN, "remote", "-v"]
        return DeveloperSecurityPolicy.execute_sandboxed("git_remote", cmd, cwd=repo_path)

    # ----------------- Confirmation-Gated Operations -----------------

    @classmethod
    def commit(cls, repo_path: Path, message: str, confirmed: bool = False) -> CommandExecutionResult:
        """Commits changes (Requires user confirmation)."""
        clean_msg = message.strip() or "Update from MacAssistant Developer Voice"
        cmd = [cls.GIT_BIN, "commit", "-am", clean_msg]
        return DeveloperSecurityPolicy.execute_sandboxed("git_commit", cmd, cwd=repo_path, confirmed=confirmed)

    @classmethod
    def push(cls, repo_path: Path, remote: str = "origin", branch: Optional[str] = None, confirmed: bool = False) -> CommandExecutionResult:
        """Pushes commits to remote (Requires user confirmation)."""
        cmd = [cls.GIT_BIN, "push", remote]
        if branch:
            cmd.append(branch)
        return DeveloperSecurityPolicy.execute_sandboxed("git_push", cmd, cwd=repo_path, timeout=60, confirmed=confirmed)

    @classmethod
    def pull(cls, repo_path: Path, remote: str = "origin", branch: Optional[str] = None, confirmed: bool = False) -> CommandExecutionResult:
        """Pulls remote changes (Requires user confirmation)."""
        cmd = [cls.GIT_BIN, "pull", remote]
        if branch:
            cmd.append(branch)
        return DeveloperSecurityPolicy.execute_sandboxed("git_pull", cmd, cwd=repo_path, timeout=60, confirmed=confirmed)

    @classmethod
    def checkout_branch(cls, repo_path: Path, branch_name: str, create: bool = False, confirmed: bool = False) -> CommandExecutionResult:
        """Switches branches (Requires user confirmation)."""
        cmd = [cls.GIT_BIN, "checkout"]
        if create:
            cmd.append("-b")
        cmd.append(branch_name)
        return DeveloperSecurityPolicy.execute_sandboxed("git_checkout", cmd, cwd=repo_path, confirmed=confirmed)

    @classmethod
    def merge(cls, repo_path: Path, source_branch: str, confirmed: bool = False) -> CommandExecutionResult:
        """Merges a branch (Requires user confirmation)."""
        cmd = [cls.GIT_BIN, "merge", source_branch]
        return DeveloperSecurityPolicy.execute_sandboxed("git_merge", cmd, cwd=repo_path, confirmed=confirmed)
