"""Project manager module for discovering, categorizing, and opening Flutter/Python projects."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .security import DeveloperSecurityPolicy, CommandExecutionResult

logger = logging.getLogger("MacAssistant.ProjectManager")


class ProjectManager:
    """
    Manages detection, categorization, and shortcuts for Flutter & Python projects:
    - Scans approved developer roots for projects.
    - Identifies project types (Flutter, Python, Hybrid).
    - Opens projects in VS Code (`code <path>`) or Finder (`open <path>`).
    """

    @staticmethod
    def inspect_project_type(path: Path) -> str:
        """Determines if a directory is a Flutter, Python, or standard project."""
        if (path / "pubspec.yaml").exists():
            return "flutter"
        if any((path / f).exists() for f in ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"]):
            return "python"
        if (path / ".venv").exists() or (path / "venv").exists():
            return "python"
        if (path / ".git").exists():
            return "git"
        return "general"

    @classmethod
    def list_projects(cls, search_root: Optional[Path] = None, limit: int = 10) -> List[Dict[str, str]]:
        """Scans approved developer folders to list recognized Flutter and Python projects."""
        root = search_root or Path("/Users/tanseer/Documents")
        valid, safe_root, _ = DeveloperSecurityPolicy.validate_project_path(root)
        if not valid or safe_root is None:
            safe_root = Path(__file__).resolve().parent.parent.parent

        projects: List[Dict[str, str]] = []

        # Always include the current workspace
        current_ws = Path(__file__).resolve().parent.parent.parent
        projects.append({
            "name": current_ws.name,
            "path": str(current_ws),
            "type": cls.inspect_project_type(current_ws)
        })

        try:
            # Look for subdirectories with pubspec.yaml or Python markers up to 3 levels deep
            for entry in safe_root.iterdir():
                if entry.is_dir() and not entry.name.startswith((".", "Library", "Applications")):
                    ptype = cls.inspect_project_type(entry)
                    if ptype in ["flutter", "python", "git"] and entry != current_ws:
                        projects.append({
                            "name": entry.name,
                            "path": str(entry),
                            "type": ptype
                        })
                    # Scan one level deeper for project folders (e.g. Documents/oopsss/...)
                    if entry.is_dir() and len(projects) < limit:
                        try:
                            for sub in entry.iterdir():
                                if sub.is_dir() and not sub.name.startswith("."):
                                    sub_type = cls.inspect_project_type(sub)
                                    if sub_type in ["flutter", "python", "git"] and sub != current_ws:
                                        projects.append({
                                            "name": sub.name,
                                            "path": str(sub),
                                            "type": sub_type
                                        })
                        except Exception:
                            pass
                if len(projects) >= limit:
                    break
        except Exception as e:
            logger.debug("Project scan error: %s", e)

        return projects[:limit]

    @classmethod
    def find_project_by_name(cls, name_query: str) -> Optional[Path]:
        """Finds a project matching a spoken name query."""
        clean_query = name_query.lower().strip()
        all_projects = cls.list_projects(limit=25)

        for proj in all_projects:
            p_name = proj["name"].lower()
            if clean_query in p_name or p_name in clean_query:
                return Path(proj["path"])

        # Check default MacAssistant workspace
        current = Path(__file__).resolve().parent.parent.parent
        if clean_query in current.name.lower():
            return current

        return None

    @classmethod
    def open_in_vscode(cls, target_path: Path) -> CommandExecutionResult:
        """Opens project in Visual Studio Code using allowlisted binary."""
        valid, safe_path, reason = DeveloperSecurityPolicy.validate_project_path(target_path)
        if not valid or safe_path is None:
            return CommandExecutionResult(
                command=["code", str(target_path)],
                returncode=-1,
                stdout="",
                stderr=f"Security check failed: {reason}",
                duration_seconds=0.0
            )

        cmd = [DeveloperSecurityPolicy.ALLOWED_BINARIES["code"], str(safe_path)]
        return DeveloperSecurityPolicy.execute_sandboxed(
            action_name="project_open_vscode",
            cmd=cmd,
            cwd=safe_path,
            timeout=10
        )

    @classmethod
    def open_in_finder(cls, target_path: Path) -> CommandExecutionResult:
        """Reveals project in macOS Finder using allowlisted /usr/bin/open."""
        valid, safe_path, reason = DeveloperSecurityPolicy.validate_project_path(target_path)
        if not valid or safe_path is None:
            return CommandExecutionResult(
                command=["open", str(target_path)],
                returncode=-1,
                stdout="",
                stderr=f"Security check failed: {reason}",
                duration_seconds=0.0
            )

        cmd = [DeveloperSecurityPolicy.ALLOWED_BINARIES["open"], str(safe_path)]
        return DeveloperSecurityPolicy.execute_sandboxed(
            action_name="project_open_finder",
            cmd=cmd,
            cwd=safe_path,
            timeout=10
        )
