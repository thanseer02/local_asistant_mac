"""Built-in Apple Shortcuts executor skill."""

import logging
import re
import subprocess
from typing import Any, Dict

from .registry import BaseSkill, SkillResult

logger = logging.getLogger("MacAssistant.Skills.Shortcuts")


class ShortcutsSkill(BaseSkill):
    name = "shortcuts"
    description = "Runs macOS Apple Shortcuts by name"
    triggers = [r"^run shortcut\s+", r"^start shortcut\s+"]

    def handle(self, utterance: str, persona: str, config: Dict[str, Any]) -> SkillResult:
        shortcut_name = re.sub(r"^(run|start)\s+shortcut\s+", "", utterance, flags=re.IGNORECASE).strip()
        if not shortcut_name:
            reply = "Which shortcut would you like me to run, Sir?" if persona.lower() == "jarvis" else "Which shortcut do you want me to run?"
            return SkillResult(handled=True, response=reply)

        try:
            cmd = ["/usr/bin/shortcuts", "run", shortcut_name]
            subprocess.Popen(cmd)
            reply = f"Executing shortcut {shortcut_name}, Sir." if persona.lower() == "jarvis" else f"Running {shortcut_name} now!"
            return SkillResult(handled=True, response=reply, action_taken="run_shortcut")
        except Exception as e:
            logger.error("Failed executing shortcut: %s", e)
            reply = f"I was unable to trigger the shortcut {shortcut_name}."
            return SkillResult(handled=True, response=reply)
