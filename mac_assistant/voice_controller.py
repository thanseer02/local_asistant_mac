"""Voice controller orchestrating microphone service, speech recognition, and command routing."""

import logging
import threading
from typing import Any, Callable, Dict, Optional

from .command_router import CommandRouter
from .config_manager import ConfigManager
from .conversation_router import ConversationRouter
from .microphone_service import MicrophoneService
from .speech_output import SpeechOutputService
from .speech_recognizer import SpeechRecognitionService

logger = logging.getLogger("MacAssistant.VoiceController")


class VoiceController:
    """
    Central controller managing voice interactions:
    - Captures speech chunks with dynamic silence detection
    - Transcribes speech via SpeechRecognitionService
    - Dispatches intents safely through CommandRouter
    - Speaks results through SpeechOutputService
    - Prevents duplicate listeners and microphone feedback loops
    """

    def __init__(
        self,
        config: Dict[str, Any],
        speech_output: SpeechOutputService,
        on_exit_requested: Optional[Callable[[], None]] = None
    ):
        self.config = config
        self.speech_output = speech_output
        self.on_exit_requested = on_exit_requested

        voice_cfg = config.get("voice_commands", {})
        thresh = float(voice_cfg.get("speech_threshold", config.get("speech_threshold", 120.0)))
        silence = float(voice_cfg.get("silence_duration", config.get("silence_duration", 1.0)))

        self.mic_service = MicrophoneService(
            speech_threshold=thresh,
            silence_duration=silence
        )
        self.recognizer = SpeechRecognitionService()
        self.router = ConversationRouter()

        self._active = False
        self._lock = threading.Lock()

    @property
    def is_listening(self) -> bool:
        return self._active

    def start(self) -> bool:
        """Starts the voice controller listening loop."""
        with self._lock:
            if self._active:
                logger.info("VoiceController is already active.")
                return True

            voice_cfg = self.config.get("voice_commands", {})
            if not voice_cfg.get("enabled", True):
                logger.info("Voice commands are disabled in configuration.")
                return False

            device_idx = voice_cfg.get("mic_index")
            success = self.mic_service.start_listening(
                on_speech_chunk=self._handle_audio_chunk,
                device_index=device_idx
            )
            if success:
                self._active = True
                logger.info("VoiceController listening successfully started.")
            return success

    def stop(self) -> None:
        """Stops the voice controller and releases microphone resources."""
        with self._lock:
            if not self._active:
                return
            self._active = False
            self.mic_service.stop_listening()
            logger.info("VoiceController listening stopped.")

    def _handle_audio_chunk(self, audio_bytes: bytes) -> None:
        """Callback invoked when user finishes an utterance."""
        logger.info("Captured voice utterance (%d bytes). Transcribing...", len(audio_bytes))

        # Transcribe audio chunk
        transcribed_text = self.recognizer.transcribe_audio_bytes(audio_bytes)
        if not transcribed_text:
            logger.info("Transcription result: (silence or unrecognized words)")
            return

        logger.info("Heard speech: '%s'", transcribed_text)
        self.process_command(transcribed_text)

    def process_command(self, utterance: str) -> None:
        """Executes a command string through the router and speaks the reply."""
        cfg = ConfigManager.load()
        persona = cfg.get("assistant_persona", "friday")
        voice = cfg.get("voice", "Moira")
        rate = cfg.get("speech_rate", 172)

        # Mute mic while speaking
        self.mic_service.set_speaking_state(True)
        try:
            intent, ok, response_text = self.router.route(utterance, persona=persona)
            logger.info("Command: '%s' -> Intent: '%s' | Response: '%s'", utterance, intent, response_text)

            # Special Control Intents
            if intent == "stop_listening":
                self.speech_output.speak(response_text, voice=voice, rate=rate)
                self.stop()
                return

            if intent == "exit":
                self.speech_output.speak(response_text, voice=voice, rate=rate)
                self.stop()
                if self.on_exit_requested:
                    self.on_exit_requested()
                return

            # Normal Action Intents
            self.speech_output.speak(response_text, voice=voice, rate=rate)

        finally:
            self.mic_service.set_speaking_state(False)
