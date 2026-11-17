"""Flutter manager module with automatic FVM detection and build/test automation."""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from .security import DeveloperSecurityPolicy, CommandExecutionResult

logger = logging.getLogger("MacAssistant.FlutterManager")


class FlutterManager:
    """
    Manages Flutter development operations:
    - Auto-detects Flutter SDK or project-specific FVM configuration (.fvm/flutter_sdk).
    - Read-only commands: doctor, analyze, test.
    - Confirmation-gated actions: pub get, build apk, build ipa.
    """

    @classmethod
    def resolve_flutter_binary(cls, project_path: Path) -> Tuple[List[str], str]:
        """
        Determines the correct invocation for Flutter:
        1. Checks if project has local `.fvm` configuration.
        2. Checks global `fvm` executable in Homebrew.
        3. Falls back to standard `flutter` in PATH.
        """
        # 1. Project-level FVM check
        if (project_path / ".fvm").exists() and Path("/opt/homebrew/bin/fvm").exists():
            return ["/opt/homebrew/bin/fvm", "flutter"], "fvm"

        # 2. Global fvm binary check
        fvm_bin = shutil.which("fvm") or "/opt/homebrew/bin/fvm"
        if Path(fvm_bin).exists():
            return [fvm_bin, "flutter"], "fvm"

        # 3. Direct flutter binary check
        flutter_bin = shutil.which("flutter") or "/opt/homebrew/bin/flutter"
        if Path(flutter_bin).exists():
            return [flutter_bin], "flutter"

        # Default fallback
        return ["flutter"], "flutter"

    @classmethod
    def doctor(cls, project_path: Path) -> CommandExecutionResult:
        """Runs flutter doctor (read-only)."""
        cmd_prefix, _ = cls.resolve_flutter_binary(project_path)
        cmd = cmd_prefix + ["doctor"]
        return DeveloperSecurityPolicy.execute_sandboxed("flutter_doctor", cmd, cwd=project_path, timeout=60)

    @classmethod
    def analyze(cls, project_path: Path) -> CommandExecutionResult:
        """Runs flutter analyze (read-only)."""
        cmd_prefix, _ = cls.resolve_flutter_binary(project_path)
        cmd = cmd_prefix + ["analyze", "--no-fatal-infos"]
        return DeveloperSecurityPolicy.execute_sandboxed("flutter_analyze", cmd, cwd=project_path, timeout=90)

    @classmethod
    def test(cls, project_path: Path, test_file: Optional[str] = None) -> CommandExecutionResult:
        """Runs flutter test (read-only)."""
        cmd_prefix, _ = cls.resolve_flutter_binary(project_path)
        cmd = cmd_prefix + ["test"]
        if test_file:
            cmd.append(test_file)
        return DeveloperSecurityPolicy.execute_sandboxed("flutter_test", cmd, cwd=project_path, timeout=120)

    # ----------------- Confirmation-Gated Operations -----------------

    @classmethod
    def pub_get(cls, project_path: Path, confirmed: bool = False) -> CommandExecutionResult:
        """Downloads/updates Flutter dependencies (Requires confirmation)."""
        cmd_prefix, _ = cls.resolve_flutter_binary(project_path)
        cmd = cmd_prefix + ["pub", "get"]
        return DeveloperSecurityPolicy.execute_sandboxed("flutter_pub_get", cmd, cwd=project_path, timeout=60, confirmed=confirmed)

    @classmethod
    def build_apk(cls, project_path: Path, release: bool = True, confirmed: bool = False) -> CommandExecutionResult:
        """Compiles Android APK (Requires confirmation)."""
        cmd_prefix, _ = cls.resolve_flutter_binary(project_path)
        cmd = cmd_prefix + ["build", "apk"]
        if release:
            cmd.append("--release")
        return DeveloperSecurityPolicy.execute_sandboxed("flutter_build_apk", cmd, cwd=project_path, timeout=300, confirmed=confirmed)

    @classmethod
    def build_ipa(cls, project_path: Path, confirmed: bool = False) -> CommandExecutionResult:
        """Compiles iOS IPA (Requires confirmation)."""
        cmd_prefix, _ = cls.resolve_flutter_binary(project_path)
        cmd = cmd_prefix + ["build", "ipa", "--no-codesign"]
        return DeveloperSecurityPolicy.execute_sandboxed("flutter_build_ipa", cmd, cwd=project_path, timeout=300, confirmed=confirmed)
