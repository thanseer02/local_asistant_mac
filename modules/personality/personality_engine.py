"""Personality engine proxy for backward compatibility. Use friday_personality and jarvis_personality."""

from modules.personality.friday_personality import FridayPersonalityEngine, PersonalityEngine

__all__ = ["FridayPersonalityEngine", "PersonalityEngine"]
