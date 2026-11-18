"""Stage 6: Text-to-Speech Engine wrapping macOS /usr/bin/say with Marvel persona cadence."""

import logging
from typing import Any, Dict, Optional

from mac_assistant.voice_engine import VoiceEngine
from .interfaces import TextToSpeechEngine

logger = logging.getLogger("MacAssistant.Pipeline.TTS")


class NativeMacTTSEngine(TextToSpeechEngine):
    """Wraps VoiceEngine with priority queuing and barge-in."""

    def __init__(self, voice_engine: Optional[VoiceEngine] = None):
        self.engine = voice_engine or VoiceEngine()

    def speak(
        self,
        text: str,
        persona: str = "friday",
        priority: str = "normal",
        play_chime: bool = True
    ) -> None:
        cfg = {"assistant_persona": persona}
        self.engine.speak(text, config=cfg, priority=priority, play_chime=play_chime)

    def stop(self) -> None:
        self.engine.stop_speaking()
