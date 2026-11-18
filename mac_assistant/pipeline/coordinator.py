"""Siri-Style On-Device Voice Pipeline Orchestrator.

Mic -> Wake word -> VAD -> STT -> Intent/LLM -> Action -> TTS -> Speaker
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from .action import PluginActionStage
from .intent import UnifiedIntentStage
from .interfaces import AudioFrame
from .stt import UnifiedSTTStage
from .tts import NativeMacTTSEngine
from .vad import EnergyVADStage
from .wake_word import OpenWakeWordStage

logger = logging.getLogger("MacAssistant.Pipeline.Coordinator")


class VoicePipelineCoordinator:
    """Coordinates the full on-device Siri-style pipeline stages."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        # Initialize modular stages
        stt_pref = config.get("stt_provider", "apple")
        self.wake_detector = OpenWakeWordStage()
        self.vad = EnergyVADStage(
            speech_threshold=float(config.get("voice_commands", {}).get("speech_threshold", 120.0)),
            silence_timeout=float(config.get("voice_commands", {}).get("silence_duration", 1.0))
        )
        self.stt = UnifiedSTTStage(preferred_provider=stt_pref)
        self.intent = UnifiedIntentStage()
        self.actions = PluginActionStage()
        self.tts = NativeMacTTSEngine()

        self._active_persona = config.get("assistant_persona", "friday")

    def process_raw_chunk(self, audio_bytes: bytes, sample_rate: int = 16000) -> Optional[str]:
        """Feeds raw chunk through wake-word, VAD, STT, Intent, and TTS."""
        frame = AudioFrame(data=audio_bytes, sample_rate=sample_rate)

        # 1. Wake word check (Offline)
        detected_persona = self.wake_detector.process_frame(frame)
        if detected_persona:
            self._active_persona = detected_persona
            logger.info("Pipeline: Wake word activated persona: %s", detected_persona)
            return detected_persona

        return None

    def execute_speech_pipeline(self, audio_bytes: bytes, persona: Optional[str] = None) -> Tuple[str, bool, str]:
        """Runs captured speech through STT -> Intent -> TTS."""
        active = persona or self._active_persona

        # 1. STT (Apple on-device Speech or Whisper)
        transcribed = self.stt.transcribe(audio_bytes)
        if not transcribed:
            return "empty", False, ""

        # 2. Intent Resolution
        intent_name, success, response_text = self.intent.resolve_intent(transcribed, persona=active)

        # 3. TTS Spoken Response
        if response_text:
            self.tts.speak(response_text, persona=active, priority="normal")

        return intent_name, success, response_text
