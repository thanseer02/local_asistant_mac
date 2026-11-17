"""Personality configuration proxy for backward compatibility. Use friday_config and jarvis_config."""

from modules.personality.friday_config import FridayPersonalityConfig, FridayPersonalityManager, PersonalityManager

__all__ = ["FridayPersonalityConfig", "FridayPersonalityManager", "PersonalityManager"]
