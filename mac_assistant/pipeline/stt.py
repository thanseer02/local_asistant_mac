"""Stage 3: Offline Speech-to-Text Providers behind a unified interface.

Providers:
- AppleSpeechProvider: Native macOS on-device Speech framework (requiresOnDeviceRecognition=true).
- WhisperProvider: faster-whisper with customized vocabulary (app names, project names, user's name).
"""

import io
import logging
from pathlib import Path
import subprocess
import tempfile
import wave
from typing import Optional

from .interfaces import SpeechToTextProvider

logger = logging.getLogger("MacAssistant.Pipeline.STT")

APPLE_STT_BIN = Path(__file__).resolve().parent / "apple_stt_bin"


class AppleSpeechProvider(SpeechToTextProvider):
    """On-device Apple Speech framework transcription."""

    def __init__(self):
        self.available = APPLE_STT_BIN.exists() and subprocess.run(["test", "-x", str(APPLE_STT_BIN)]).returncode == 0

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not self.available or not audio_bytes:
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            try:
                res = subprocess.run([str(APPLE_STT_BIN), tmp.name], capture_output=True, text=True, timeout=5.0)
                text = res.stdout.strip()
                if text:
                    logger.info("Apple On-Device Speech transcribed: '%s'", text)
                    return text
            except Exception as e:
                logger.debug("Apple STT execution fallback: %s", e)

        return ""


class WhisperSpeechProvider(SpeechToTextProvider):
    """Local Faster-Whisper provider with custom hotwords/vocabulary."""

    def __init__(self, model_size: str = "tiny.en"):
        self.model_size = model_size
        self._model = None
        self.initial_prompt = "Chrome, VS Code, Antigravity, Spotify, Terminal, Brave, Tanseer, Jarvis, Friday"

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info("Loading offline Whisper model '%s' with custom vocabulary...", self.model_size)
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not audio_bytes:
            return ""

        self._ensure_model()
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)
        bio.seek(0)

        segments, _ = self._model.transcribe(
            bio,
            beam_size=1,
            initial_prompt=self.initial_prompt,
            vad_filter=True
        )
        text = " ".join([seg.text for seg in segments]).strip()
        if text:
            logger.info("Whisper transcribed: '%s'", text)
        return text


class UnifiedSTTStage(SpeechToTextProvider):
    """Unified STT stage defaulting to Apple On-Device Speech with fallback to Whisper."""

    def __init__(self, preferred_provider: str = "apple"):
        self.preferred_provider = preferred_provider
        self.apple = AppleSpeechProvider()
        self.whisper = WhisperSpeechProvider()

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if self.preferred_provider == "apple" and self.apple.available:
            text = self.apple.transcribe(audio_bytes, sample_rate=sample_rate)
            if text:
                return text
        return self.whisper.transcribe(audio_bytes, sample_rate=sample_rate)
