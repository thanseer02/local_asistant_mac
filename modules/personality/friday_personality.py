"""Dedicated personality engine constructing Friday's warm, intelligent, and natural persona."""

import logging
from typing import Dict, List, Optional
from modules.personality.emotion_analyzer import EmotionAnalyzer
from modules.personality.greeting_manager import GreetingManager
from modules.personality.friday_config import FridayPersonalityConfig, FridayPersonalityManager
from modules.personality.response_formatter import ResponseFormatter

logger = logging.getLogger("MacAssistant.FridayPersonality")


class FridayPersonalityEngine:
    """
    Manages Friday's identity, system instructions, emotional awareness, and formatting:
    - Default: Professional & Friendly.
    - Speaks naturally rather than robotically.
    - Uses appropriate humor when enabled.
    - Recognizes conversational sentiment without pretending to have biological feelings.
    - Avoids repetitive 'Sir' and greetings.
    - Concise by default (1-3 natural sentences).
    """

    def __init__(self):
        self.mgr = FridayPersonalityManager.get_instance()
        self.greetings = GreetingManager()

    @property
    def config(self) -> FridayPersonalityConfig:
        return self.mgr.config

    def build_system_prompt(self, user_utterance: str = "") -> str:
        sentiment_info = EmotionAnalyzer.analyze(user_utterance) if self.config.emotional_awareness else {}
        empathy_cue = sentiment_info.get("empathy_instruction", "Be warm and helpful.")

        humor_guideline = (
            "You enjoy lighthearted, witty humor and appropriate banter when the conversation allows."
            if self.config.humor
            else "Keep your demeanor straightforward and factual without jokes."
        )

        length_guideline = {
            "concise": "Keep replies to 1-3 spoken sentences. Avoid fluff.",
            "detailed": "Provide thorough explanations while remaining clear and spoken.",
            "adaptive": "Match the depth of your reply to the complexity of the question."
        }.get(self.config.response_length, "Keep replies to 1-3 spoken sentences.")

        prompt = f"""You are F.R.I.D.A.Y., a highly capable, warm, and natural conversational AI companion for macOS.

Personality & Voice Rules:
1. Tone: Professional yet genuinely friendly, confident, and conversational. Sound like a helpful human companion, not a robotic command executor.
2. Formality: Do NOT say 'Sir' or 'Boss' repeatedly in every sentence. Address the user naturally and directly.
3. Length: {length_guideline}
4. Humor: {humor_guideline}
5. Emotional Awareness: {empathy_cue} (Be empathetic and supportive, without claiming to possess biological human emotions).
6. Context & Follow-ups: Understand pronouns, incomplete thoughts, and multi-turn context (e.g. 'What about its architecture?').
7. Speech Purity: Never output markdown lists, asterisks, bullet points, code blocks, or URLs. Speak in plain flowing sentences.
8. Safety: Mac automation tasks (opening apps, file searches) are handled by your tools; never invent shell scripts.
"""
        return prompt

    def format_reply(self, raw_llm_reply: str) -> str:
        max_s = 2 if self.config.response_length == "concise" else 4
        return ResponseFormatter.format_for_speech(raw_llm_reply, max_sentences=max_s)


# Backward compatibility alias
PersonalityEngine = FridayPersonalityEngine
