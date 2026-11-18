"""Built-in memory and recall skill wrapping MemoryStore."""

import logging
import re
from typing import Any, Dict

from mac_assistant.memory_store import MemoryStore
from .registry import BaseSkill, SkillResult

logger = logging.getLogger("MacAssistant.Skills.Memory")


class MemorySkill(BaseSkill):
    name = "memory"
    description = "Stores, recalls, and forgets facts in local SQLite memory"
    triggers = [
        r"^remember that\s+", r"^note that\s+",
        r"^what do you remember about\s+", r"^what did i tell you about\s+",
        r"^forget\s+"
    ]

    def __init__(self):
        self.store = MemoryStore()

    def handle(self, utterance: str, persona: str, config: Dict[str, Any]) -> SkillResult:
        clean = utterance.strip()

        # 1. Store Fact
        remember_match = re.search(r"^(?:please\s+)?(?:remember|note)\s+that\s+(.+)", clean, re.IGNORECASE)
        if remember_match:
            fact = remember_match.group(1).strip()
            topic = fact.split()[0] if fact.split() else "general"
            ok, due_time = self.store.remember(topic, fact)
            if ok:
                time_note = f" I will remind you at {due_time}." if due_time else ""
                if persona.lower() == "jarvis":
                    reply = f"I have committed that to memory, Sir.{time_note}"
                else:
                    reply = f"Got it! I've noted that down.{time_note}"
                return SkillResult(handled=True, response=reply, action_taken="remember")

        # 2. Recall Fact
        recall_match = re.search(r"^(?:what do you remember about|what did i tell you about)\s+(.+)", clean, re.IGNORECASE)
        if recall_match:
            query = recall_match.group(1).strip("?. ")
            facts = self.store.recall(query)
            if facts:
                top_fact = facts[0]["fact"]
                if persona.lower() == "jarvis":
                    reply = f"Here is what my memory holds, Sir: {top_fact}"
                else:
                    reply = f"Here's what I remember: {top_fact}"
                return SkillResult(handled=True, response=reply, action_taken="recall")
            else:
                reply = f"I have no prior records regarding {query}, Sir." if persona.lower() == "jarvis" else f"I couldn't find anything in my notes about {query}."
                return SkillResult(handled=True, response=reply, action_taken="recall_empty")

        # 3. Forget Fact
        forget_match = re.search(r"^forget\s+(.+)", clean, re.IGNORECASE)
        if forget_match:
            topic = forget_match.group(1).strip("?. ")
            deleted = self.store.forget(topic)
            if deleted > 0:
                reply = f"Understood, Sir. I have cleared those records from memory." if persona.lower() == "jarvis" else "All done! I've removed that from my notes."
            else:
                reply = f"There were no matching records to expunge, Sir." if persona.lower() == "jarvis" else "I didn't find any notes matching that."
            return SkillResult(handled=True, response=reply, action_taken="forget")

        return SkillResult(handled=False, response="")
