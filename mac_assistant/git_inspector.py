"""Git repository inspector for developer briefings."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MacAssistant.GitInspector")


class GitInspector:
    """Inspects configured git repositories for uncommitted changes and unmerged/ahead branches."""

    @staticmethod
    def inspect_repo(repo_path: Path) -> Optional[Dict[str, Any]]:
        """Checks a git repository for dirty files and unpushed/unmerged branches."""
        if not repo_path.exists() or not (repo_path / ".git").exists():
            return None

        repo_name = repo_path.name
        uncommitted_count = 0
        branch_info = ""

        try:
            # 1. Check uncommitted changes (modified, untracked, staged)
            status_res = subprocess.run(
                ["/usr/bin/git", "-C", str(repo_path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if status_res.returncode == 0:
                lines = [line for line in status_res.stdout.splitlines() if line.strip()]
                uncommitted_count = len(lines)

            # 2. Check current branch and ahead/unmerged status
            branch_res = subprocess.run(
                ["/usr/bin/git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3
            )
            current_branch = branch_res.stdout.strip() if branch_res.returncode == 0 else "main"

            # Check if ahead of upstream
            ahead_res = subprocess.run(
                ["/usr/bin/git", "-C", str(repo_path), "rev-list", f"@{'{u}'}..HEAD", "--count"],
                capture_output=True,
                text=True,
                timeout=3
            )
            ahead_count = int(ahead_res.stdout.strip()) if ahead_res.returncode == 0 and ahead_res.stdout.strip().isdigit() else 0

            return {
                "name": repo_name,
                "uncommitted_count": uncommitted_count,
                "current_branch": current_branch,
                "ahead_count": ahead_count
            }
        except Exception as e:
            logger.debug("Failed inspecting git repo at %s: %s", repo_path, e)
            return None

    @classmethod
    def get_summary(cls, config: Dict[str, Any]) -> str:
        """Inspects all configured repositories and formats a natural audio briefing sentence."""
        git_cfg = config.get("git_briefing", {})
        if not git_cfg.get("enabled", True):
            return ""

        paths_to_check = git_cfg.get("repositories", [])
        if not paths_to_check:
            # Default to current project directory
            paths_to_check = [str(Path(__file__).resolve().parent.parent)]

        summaries = []
        for path_str in paths_to_check:
            info = cls.inspect_repo(Path(path_str).expanduser())
            if not info:
                continue

            name = info["name"]
            uncommitted = info["uncommitted_count"]
            ahead = info["ahead_count"]

            parts = []
            if uncommitted > 0:
                file_word = "file" if uncommitted == 1 else "files"
                parts.append(f"{uncommitted} uncommitted {file_word}")

            if ahead > 0:
                commit_word = "commit" if ahead == 1 else "commits"
                parts.append(f"{ahead} {commit_word} waiting to be pushed")

            if parts:
                summaries.append(f"in {name}, you have {' and '.join(parts)}")

        if not summaries:
            return ""

        persona_key = config.get("assistant_persona", "friday").lower()
        summary_str = "; and ".join(summaries)

        if persona_key == "jarvis":
            return f"As a developer update, {summary_str}."
        else:
            return f"Developer check: {summary_str}."
