"""Emotion and sentiment analyzer for natural human conversational awareness."""

import re
from typing import Dict, Tuple


class EmotionAnalyzer:
    """
    Analyzes conversational sentiment and cues:
    Detects frustration, excitement, urgency, fatigue, curiosity, or neutral intent.
    Helps Friday calibrate empathy and warmth without pretending to be a biological human.
    """

    FRUSTRATION_KEYWORDS = [
        "annoyed", "frustrated", "not working", "broken", "hate this",
        "stupid", "ugh", "terrible", "awful", "failed again", "why won't you"
    ]
    EXCITEMENT_KEYWORDS = [
        "awesome", "great", "amazing", "cool", "fantastic", "wonderful",
        "love it", "hurray", "yay", "super", "brilliant"
    ]
    FATIGUE_KEYWORDS = [
        "tired", "exhausted", "sleepy", "long day", "burnout", "headache", "drained"
    ]
    URGENCY_KEYWORDS = [
        "quick", "fast", "urgent", "asap", "hurry", "right now", "immediately"
    ]

    @classmethod
    def analyze(cls, text: str) -> Dict[str, any]:
        lower = text.lower()

        if any(w in lower for w in cls.FRUSTRATION_KEYWORDS):
            return {
                "sentiment": "frustrated",
                "empathy_instruction": "Acknowledge the difficulty with calm reassurance; be direct and helpful."
            }

        if any(w in lower for w in cls.EXCITEMENT_KEYWORDS):
            return {
                "sentiment": "excited",
                "empathy_instruction": "Match the user's positive energy warmly and encouragingly."
            }

        if any(w in lower for w in cls.FATIGUE_KEYWORDS):
            return {
                "sentiment": "fatigued",
                "empathy_instruction": "Be gentle, concise, and supportive; don't burden with unnecessary questions."
            }

        if any(w in lower for w in cls.URGENCY_KEYWORDS):
            return {
                "sentiment": "urgent",
                "empathy_instruction": "Keep response ultra-short, crisp, and direct to the point."
            }

        return {
            "sentiment": "neutral_curious",
            "empathy_instruction": "Maintain friendly, clear, and intelligent conversational warmth."
        }
