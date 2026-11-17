"""Speech recognition service using local faster-whisper (offline, low-latency, accurate)."""

import io
import logging
import tempfile
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger("MacAssistant.SpeechRecognizer")


class SpeechRecognitionService:
    """
    Offline local speech recognizer powered by faster-whisper.
    Zero cloud dependencies. Fast and accurate on Apple Silicon.
    """

    def __init__(self, sample_rate: int = 16000, model_size: str = "tiny.en"):
        self.sample_rate = sample_rate
        self.model_size = model_size
        self._model = None
        self._init_model()

    def _init_model(self) -> None:
        """Loads faster-whisper model locally."""
        try:
            from faster_whisper import WhisperModel
            logger.info("Initializing offline faster-whisper model ('%s')...", self.model_size)
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            logger.info("faster-whisper model loaded and ready.")
        except Exception as e:
            logger.error("Failed to load faster-whisper: %s", e)

    def transcribe_audio_bytes(self, audio_data: bytes) -> Optional[str]:
        """Transcribes raw PCM audio bytes to clean English text using local Whisper."""
        if not audio_data or len(audio_data) < 12000:  # Minimum audio length
            return None

        if self._model is None:
            self._init_model()
            if self._model is None:
                return None

        # Write to temporary wav for faster-whisper input
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data)

            segments, info = self._model.transcribe(
                str(tmp_path),
                beam_size=1,
                language="en",
                initial_prompt="Friday, Jarvis, Hey Friday, Hey Jarvis.",
                condition_on_previous_text=False,
                vad_filter=True
            )

            text_parts = [s.text.strip() for s in segments if s.text.strip()]
            full_text = " ".join(text_parts).strip()

            if full_text:
                logger.info("Local Whisper transcribed: '%s' (prob=%.2f)", full_text, info.language_probability)
                return full_text
            return None

        except Exception as e:
            logger.error("Whisper transcription error: %s", e)
            return None
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
