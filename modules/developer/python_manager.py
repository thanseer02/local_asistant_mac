"""Python manager module for virtual environment detection, script execution, and pytest."""

import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from .security import DeveloperSecurityPolicy, CommandExecutionResult

logger = logging.getLogger("MacAssistant.PythonManager")


class PythonManager:
    """
    Manages Python project tasks:
    - Auto-detects local virtual environments (.venv, venv, or active sys.executable).
    - Runs pytest and parses tracebacks.
    - Executes approved project scripts with confirmation.
    """

    @classmethod
    def detect_venv(cls, project_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Locates the virtual environment directory and its python binary:
        Returns: (venv_dir, python_bin)
        """
        candidates = [
            project_path / ".venv",
            project_path / "venv",
            project_path / "env",
            Path(__file__).resolve().parent.parent.parent / "venv"
        ]

        for venv in candidates:
            if venv.exists() and venv.is_dir():
                py_bin = venv / "bin" / "python"
                if py_bin.exists():
                    return venv, py_bin

        # Fallback to system python3
        return None, Path(sys.executable)

    @classmethod
    def run_pytest(cls, project_path: Path, test_target: Optional[str] = None) -> CommandExecutionResult:
        """Runs pytest using project virtual environment or python -m unittest fallback."""
        _, py_bin = cls.detect_venv(project_path)
        py_exec = str(py_bin) if py_bin else "python3"

        # Check if pytest is available in venv
        pytest_bin = py_bin.parent / "pytest" if py_bin else None
        if pytest_bin and pytest_bin.exists():
            cmd = [str(pytest_bin)]
            if test_target:
                cmd.append(test_target)
        else:
            # Fallback to python -m unittest
            cmd = [py_exec, "-m", "unittest"]
            if test_target:
                cmd.append(test_target)

        return DeveloperSecurityPolicy.execute_sandboxed("python_pytest", cmd, cwd=project_path, timeout=60)

    @classmethod
    def run_approved_script(cls, project_path: Path, script_rel_path: str, confirmed: bool = False) -> CommandExecutionResult:
        """
        Runs an approved Python script within the project (Requires confirmation).
        Enforces path containment within project.
        """
        target_script = (project_path / script_rel_path).resolve()
        if not target_script.exists():
            return CommandExecutionResult(
                command=["python", script_rel_path],
                returncode=-1,
                stdout="",
                stderr=f"Script does not exist: {script_rel_path}",
                duration_seconds=0.0
            )

        if not str(target_script).startswith(str(project_path)):
            return CommandExecutionResult(
                command=["python", script_rel_path],
                returncode=-1,
                stdout="",
                stderr="Script must be located inside the project directory.",
                duration_seconds=0.0
            )

        _, py_bin = cls.detect_venv(project_path)
        py_exec = str(py_bin) if py_bin else "python3"

        cmd = [py_exec, str(target_script)]
        return DeveloperSecurityPolicy.execute_sandboxed("python_run_script", cmd, cwd=project_path, timeout=120, confirmed=confirmed)
