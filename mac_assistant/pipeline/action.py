"""Stage 5: Plugin-Style Action Registry.

Supports:
- Apple Shortcuts via `shortcuts run "<name>"`
- AppleScript automation
- Shell execution (with voice/PIN confirmation for sensitive commands)
"""

import logging
import subprocess
from typing import Any, Callable, Dict, Optional, Tuple

from mac_assistant.security_service import SecurityConfirmationService
from .interfaces import ActionExecutor

logger = logging.getLogger("MacAssistant.Pipeline.Action")


class PluginActionStage(ActionExecutor):
    """Executes registered actions and system automations."""

    def __init__(self):
        self._registry: Dict[str, Callable[..., Tuple[bool, str]]] = {}
        self._register_default_actions()

    def register_action(self, name: str, func: Callable[..., Tuple[bool, str]]) -> None:
        self._registry[name] = func

    def _register_default_actions(self) -> None:
        self._registry["run_shortcut"] = self._run_shortcut
        self._registry["run_applescript"] = self._run_applescript
        self._registry["run_shell"] = self._run_shell

    def _run_shortcut(self, shortcut_name: str) -> Tuple[bool, str]:
        try:
            cmd = ["/usr/bin/shortcuts", "run", shortcut_name]
            subprocess.Popen(cmd)
            return True, f"Running shortcut: {shortcut_name}."
        except Exception as e:
            return False, f"Could not run shortcut: {e}"

    def _run_applescript(self, script: str) -> Tuple[bool, str]:
        try:
            res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=5.0)
            return res.returncode == 0, res.stdout.strip()
        except Exception as e:
            return False, str(e)

    def _run_shell(self, command: str, sensitive: bool = False, pin: Optional[str] = None) -> Tuple[bool, str]:
        if sensitive:
            if not pin or not SecurityConfirmationService.verify_voice_pin(pin):
                return False, "Security verification required. Action blocked."
        try:
            res = subprocess.run(command.split(), capture_output=True, text=True, timeout=5.0)
            return res.returncode == 0, res.stdout.strip()
        except Exception as e:
            return False, str(e)

    def execute(self, action_name: str, **kwargs) -> Tuple[bool, str]:
        if action_name in self._registry:
            return self._registry[action_name](**kwargs)
        return False, f"Action '{action_name}' is not registered."
