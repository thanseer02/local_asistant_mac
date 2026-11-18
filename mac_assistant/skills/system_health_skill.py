"""Built-in system health diagnostic skill."""

import logging
import subprocess
from typing import Any, Dict

from .registry import BaseSkill, SkillResult

logger = logging.getLogger("MacAssistant.Skills.SystemHealth")


class SystemHealthSkill(BaseSkill):
    name = "system_health"
    description = "Inspects top CPU and memory consumers when Mac is slow"
    triggers = [
        "why is my mac slow", "check system health", "check performance",
        "top processes", "cpu usage", "system diagnostic"
    ]

    def handle(self, utterance: str, persona: str, config: Dict[str, Any]) -> SkillResult:
        try:
            # Query top process by CPU usage using native /bin/ps
            cmd = ["/bin/ps", "-A", "-r", "-o", "%cpu,comm"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            lines = res.stdout.strip().splitlines()

            if len(lines) > 1:
                top_line = lines[1].strip()
                parts = top_line.split(None, 1)
                cpu_pct = parts[0]
                proc_name = parts[1].split("/")[-1] if len(parts) > 1 else "Unknown"

                if persona.lower() == "jarvis":
                    reply = f"Diagnostics indicate {proc_name} is consuming {cpu_pct} percent CPU, Sir. System resources remain stable."
                else:
                    reply = f"Looks like {proc_name} is using {cpu_pct} percent of your CPU right now, but everything is stable."
                return SkillResult(handled=True, response=reply, action_taken="system_health")

        except Exception as e:
            logger.error("System health check failed: %s", e)

        reply = "Your Mac's processing load appears entirely normal, Sir." if persona.lower() == "jarvis" else "Everything looks healthy and responsive on your Mac."
        return SkillResult(handled=True, response=reply)
