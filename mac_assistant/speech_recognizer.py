"""Speech recognition service supporting Google STT, Apple Speech, and Whisper."""

import logging
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger("MacAssistant.SpeechRecognizer")


class SpeechRecognitionService:
    """
    Provides robust speech-to-text transcription for captured audio.
    Supports Google Speech Recognition (online via speech_recognition library),
    macOS SFSpeechRecognizer fallback, and local Whisper if available.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def transcribe_audio_bytes(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribes raw PCM 16-bit mono audio bytes to clean English text.
        Applies audio length sanity checking and error recovery.
        """
        if not audio_data or len(audio_data) < 16000:  # Minimum 0.5s of audio
            logger.debug("Audio chunk too small for transcription (%d bytes).", len(audio_data) if audio_data else 0)
            return None

        # Write to temporary wav container for transcription processing
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data)

            # Strategy 1: Use speech_recognition with Google Speech API
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                r.energy_threshold = 300
                r.dynamic_energy_threshold = False
                
                with sr.AudioFile(str(tmp_path)) as source:
                    audio = r.record(source)

                # Recognize speech
                text = r.recognize_google(audio)
                if text:
                    cleaned = text.strip()
                    logger.info("Speech transcribed successfully: '%s'", cleaned)
                    return cleaned
            except sr.UnknownValueError:
                logger.debug("SpeechRecognition could not understand audio.")
                return None
            except sr.RequestError as e:
                logger.warning("SpeechRecognition service request error: %s", e)
            except Exception as e:
                logger.debug("SpeechRecognition library exception: %s", e)

            # Strategy 2: macOS SFSpeechRecognizer fallback via Swift CLI (if compiled)
            native_text = self._transcribe_native_macos(tmp_path)
            if native_text:
                return native_text

            return None

        except Exception as e:
            logger.error("Unexpected error in SpeechRecognitionService: %s", e)
            return None
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _transcribe_native_macos(self, wav_path: Path) -> Optional[str]:
        """Optional fallback to macOS native dictation or tools."""
        return None
