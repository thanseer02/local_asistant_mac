"""Extensible plugin skills registry for MacAssistant.

Each skill declares triggers (regex or keywords), a handler, and description.
Skills are auto-discovered and enabled/disabled in config.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import importlib
import logging
import pkgutil
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("MacAssistant.Skills")


@dataclass
class SkillResult:
    handled: bool
    response: str
    action_taken: Optional[str] = None


class BaseSkill(ABC):
    """Base class for pluggable skills."""

    name: str = "base"
    description: str = "Base Skill"
    triggers: List[str] = []

    @abstractmethod
    def handle(self, utterance: str, persona: str, config: Dict[str, Any]) -> SkillResult:
        """Executes the skill if triggered."""
        pass

    def matches(self, utterance: str) -> bool:
        """Returns True if the utterance matches any declared trigger."""
        clean = utterance.strip().lower()
        for trig in self.triggers:
            if trig.startswith("^") or trig.endswith("$") or r"\b" in trig:
                if re.search(trig, clean, re.IGNORECASE):
                    return True
            else:
                if trig.lower() in clean:
                    return True
        return False


class SkillRegistry:
    """Manages skill discovery, configuration, and dispatch."""

    def __init__(self):
        self._skills: List[BaseSkill] = []
        self._discover_skills()

    def _discover_skills(self) -> None:
        """Dynamically imports all skill subclasses in mac_assistant/skills/."""
        pkg_path = Path(__file__).resolve().parent
        for _, module_name, _ in pkgutil.iter_modules([str(pkg_path)]):
            if module_name.startswith("_") or module_name == "registry":
                continue
            try:
                mod = importlib.import_module(f"mac_assistant.skills.{module_name}")
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if isinstance(obj, type) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                        instance = obj()
                        self._skills.append(instance)
                        logger.debug("Discovered skill: %s (%s)", instance.name, instance.description)
            except Exception as e:
                logger.error("Error loading skill '%s': %s", module_name, e)

    def dispatch(self, utterance: str, persona: str, config: Dict[str, Any]) -> SkillResult:
        """Dispatches utterance across enabled skills in registry."""
        skills_cfg = config.get("skills", {})

        for skill in self._skills:
            # Check if enabled in config (default true)
            if not skills_cfg.get(skill.name, True):
                continue

            if skill.matches(utterance):
                logger.info("Dispatching command '%s' to skill: %s", utterance, skill.name)
                try:
                    result = skill.handle(utterance, persona, config)
                    if result.handled:
                        return result
                except Exception as e:
                    logger.error("Error in skill '%s': %s", skill.name, e)

        # Unknown commands fallback
        if persona.lower() == "jarvis":
            fallback = "My apologies, Sir. I didn't quite catch that."
        else:
            fallback = "Sorry about that! I didn't quite catch what you said."

        return SkillResult(handled=False, response=fallback)
