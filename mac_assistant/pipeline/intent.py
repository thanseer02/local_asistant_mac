"""Stage 4: Unified Intent Layer.

Routes fast rule-based commands first, then falls back to local on-device LLM
with function/tool calling and short conversation memory.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from mac_assistant.context_service import ContextAwarenessService
from mac_assistant.conversation_router import ConversationRouter
from .interfaces import IntentResolver

logger = logging.getLogger("MacAssistant.Pipeline.Intent")


class UnifiedIntentStage(IntentResolver):
    """Orchestrates fast rule matching and local LLM with tool calling."""

    def __init__(self):
        self.router = ConversationRouter()

    def resolve_intent(
        self,
        utterance: str,
        persona: str = "friday",
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, bool, str]:
        logger.info("Pipeline Intent: Resolving utterance '%s' for persona '%s'", utterance, persona)
        return self.router.route(utterance, persona=persona)
