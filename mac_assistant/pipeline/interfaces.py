"""Siri-Style On-Device Voice Pipeline Interfaces.

Defines the pluggable stages:
Mic -> Wake Word -> VAD -> STT -> Intent/LLM -> Action -> TTS -> Speaker
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class AudioFrame:
    """Raw audio frame data."""
    data: bytes
    sample_rate: int
    channels: int = 1


class WakeWordDetector(ABC):
    """Stage 1: Offline wake-word detector on a shared stream."""

    @abstractmethod
    def process_frame(self, frame: AudioFrame) -> Optional[str]:
        """Processes frame, returning persona name ('jarvis', 'friday') or None."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets detector state."""
        pass


class VoiceActivityDetector(ABC):
    """Stage 2: Voice Activity Detection (VAD) determining speech start and end."""

    @abstractmethod
    def is_speech(self, frame: AudioFrame) -> bool:
        """Returns True if the frame contains active human speech."""
        pass

    @abstractmethod
    def reset(self) -> None:
        pass


class SpeechToTextProvider(ABC):
    """Stage 3: Offline speech-to-text transcription."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcribes speech audio into text."""
        pass


class IntentResolver(ABC):
    """Stage 4: Rule-based router + local LLM with tool calling."""

    @abstractmethod
    def resolve_intent(
        self,
        utterance: str,
        persona: str = "friday",
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, bool, str]:
        """Resolves utterance into (intent_name, success, response_text)."""
        pass


class ActionExecutor(ABC):
    """Stage 5: Plugin-style action execution (Shortcuts, AppleScript, system tools)."""

    @abstractmethod
    def execute(self, action_name: str, **kwargs) -> Tuple[bool, str]:
        pass


class TextToSpeechEngine(ABC):
    """Stage 6: Spoken response synthesis with Marvel persona voices."""

    @abstractmethod
    def speak(
        self,
        text: str,
        persona: str = "friday",
        priority: str = "normal",
        play_chime: bool = True
    ) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        """Immediate barge-in / stop playback."""
        pass
