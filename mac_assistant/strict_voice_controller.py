"""Strict wake-word state manager implementing STANDBY -> WAKE_WORD_DETECTED -> LISTENING -> PROCESSING -> SPEAKING."""

import enum
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

from .config_manager import ConfigManager
from .conversation_router import ConversationRouter
from .microphone_service import MicrophoneService
from .speech_output import SpeechOutputService
from .speech_recognizer import SpeechRecognitionService
from .wake_word_service import WakeWordService

logger = logging.getLogger("MacAssistant.StrictVoiceController")


class AssistantState(enum.Enum):
    STANDBY = "STANDBY"
    WAKE_WORD_DETECTED = "WAKE_WORD_DETECTED"
    LISTENING_FOR_COMMAND = "LISTENING_FOR_COMMAND"
    PROCESSING_COMMAND = "PROCESSING_COMMAND"
    SPEAKING_RESPONSE = "SPEAKING_RESPONSE"


class StrictVoiceController:
    """
    Manages strict wake-word activation workflow:
    1. STANDBY mode: lightweight wake detection only (openWakeWord / acoustic detector).
    2. WAKE_WORD_DETECTED: Triggers short activation chime ('hud_chime.wav').
    3. LISTENING_FOR_COMMAND: Captures command utterance with silence timeout.
    4. PROCESSING_COMMAND: Transcribes with Faster-Whisper, executes approved tool or Ollama chat.
    5. SPEAKING_RESPONSE: Speaks output via speech engine with mic muted to prevent self-triggering.
    6. Automatically returns to STANDBY mode.
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

        self.state = AssistantState.STANDBY
        self._lock = threading.Lock()
        self._running = False

        voice_cfg = config.get("voice_commands", {})
        self.speech_threshold = float(voice_cfg.get("speech_threshold", 120.0))
        self.command_silence_duration = float(voice_cfg.get("silence_duration", 1.0))
        self.command_timeout = float(voice_cfg.get("command_timeout", 6.0))

        # Core Engines
        self.wake_detector = WakeWordService(
            jarvis_threshold=float(voice_cfg.get("wake_sensitivity", 0.5)),
            friday_threshold=float(voice_cfg.get("wake_sensitivity", 0.5))
        )
        self.mic_service = MicrophoneService(
            speech_threshold=self.speech_threshold,
            silence_duration=self.command_silence_duration
        )
        self.recognizer = SpeechRecognitionService()
        self.router = ConversationRouter()

        # Command capture buffers
        self._command_audio_chunks = []
        self._active_wake_persona: Optional[str] = None

    @property
    def current_state(self) -> str:
        return self.state.value

    def start(self) -> bool:
        """Starts the microphone and standby wake-word detection loop."""
        with self._lock:
            if self._running:
                return True
            self._running = True
            self.state = AssistantState.STANDBY

            voice_cfg = self.config.get("voice_commands", {})
            if not voice_cfg.get("enabled", True):
                logger.info("Voice commands disabled in config.")
                return False

            device_idx = voice_cfg.get("mic_index")
            # Connect mic stream to our raw audio frame processor
            success = self.mic_service.start_listening(
                on_speech_chunk=self._on_audio_chunk,
                device_index=device_idx
            )
            if success:
                logger.info("Assistant started in STANDBY mode. Listening strictly for 'Friday' or 'Jarvis'.")
            return success

    def stop(self) -> None:
        """Halts the voice controller cleanly."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self.state = AssistantState.STANDBY
            self.mic_service.stop_listening()
            logger.info("StrictVoiceController stopped.")

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        """
        Invoked on each captured speech chunk from the microphone.
        Enforces strict state transitions.
        """
        # 1. Guard against microphone feedback while assistant is speaking
        if self.state == AssistantState.SPEAKING_RESPONSE or self.mic_service._is_speaking:
            logger.debug("Audio chunk ignored: assistant is currently speaking.")
            return

        # 2. STANDBY MODE: Only wake words ('Friday' or 'Jarvis') can transition state
        if self.state == AssistantState.STANDBY:
            detected_wake = self._detect_wake_word_in_audio(audio_bytes)
            if not detected_wake:
                # Completely ignore background talk, TV noise, random speech without wake word
                logger.debug("STANDBY: Audio ignored (no wake word detected).")
                return

            wake_word, immediate_command = detected_wake
            logger.info("Wake word detected: '%s' (Immediate command: '%s')", wake_word, immediate_command)

            with self._lock:
                self.state = AssistantState.WAKE_WORD_DETECTED
                self._active_wake_persona = wake_word

            # Play short activation HUD chime
            self.speech_output.play_hud_chime("hud_chime.wav")

            if immediate_command:
                # User said "Friday, open Chrome" in one utterance
                self._execute_command_pipeline(immediate_command, persona=wake_word)
            else:
                # User said "Friday" -> Prompt user and transition to LISTENING_FOR_COMMAND
                prompt_reply = "Yes, Sir?" if wake_word == "jarvis" else "Yes, Boss?"
                self.state = AssistantState.SPEAKING_RESPONSE
                self.mic_service.set_speaking_state(True)
                cfg = ConfigManager.load()
                personas_cfg = cfg.get("personas", {})
                if wake_word == "jarvis":
                    j_voice = personas_cfg.get("jarvis", {}).get("voice", "Daniel")
                    j_rate = personas_cfg.get("jarvis", {}).get("speech_rate", 162)
                    prompt_voice, prompt_rate = j_voice, j_rate
                else:
                    f_voice = personas_cfg.get("friday", {}).get("voice", cfg.get("voice", "Moira"))
                    f_rate = personas_cfg.get("friday", {}).get("speech_rate", cfg.get("speech_rate", 172))
                    prompt_voice, prompt_rate = f_voice, f_rate

                try:
                    self.speech_output.speak(prompt_reply, voice=prompt_voice, rate=prompt_rate, play_chime=False)
                finally:
                    self.mic_service.set_speaking_state(False)

                with self._lock:
                    self.state = AssistantState.LISTENING_FOR_COMMAND
                    logger.info("Transitioned to LISTENING_FOR_COMMAND. Awaiting user instruction...")

            return

        # 3. LISTENING_FOR_COMMAND MODE: Capture user instruction
        if self.state == AssistantState.LISTENING_FOR_COMMAND:
            with self._lock:
                self.state = AssistantState.PROCESSING_COMMAND

            logger.info("Transcribing captured command with Faster-Whisper...")
            command_text = self.recognizer.transcribe_audio_bytes(audio_bytes)

            if not command_text or len(command_text.strip()) < 2:
                logger.info("No clear command transcribed. Returning to STANDBY.")
                self.state = AssistantState.STANDBY
                return

            persona = self._active_wake_persona or self.config.get("assistant_persona", "friday")
            self._execute_command_pipeline(command_text, persona=persona)

    def _detect_wake_word_in_audio(self, audio_bytes: bytes) -> Optional[Tuple[str, Optional[str]]]:
        """
        Strictly tests audio chunk for 'Friday' or 'Jarvis'.
        1. Fast test via openWakeWord ONNX for 'jarvis'.
        2. Fast transcription via Whisper for 'friday' or 'jarvis'.
        Returns (wake_word, follow_up_command) if detected, else None.
        """
        # Step A: Check openWakeWord model for Jarvis
        try:
            samples = np.frombuffer(audio_bytes, dtype=np.int16)
            if len(samples) >= 1280:
                frame = samples[-1280:]
                oww_result = self.wake_detector.process_frame(frame)
                if oww_result == "jarvis":
                    return "jarvis", None
        except Exception:
            pass

        # Step B: Fast transcription check for 'Friday' or 'Jarvis'
        text = self.recognizer.transcribe_audio_bytes(audio_bytes)
        if not text:
            return None

        clean = text.lower().strip(",.!? ")

        # Test Jarvis
        if "jarvis" in clean or "hey jarvis" in clean:
            # Extract following command if present
            m = re.search(r"(?:hey\s+)?jarvis[,:\s]*(.*)", clean)
            cmd = m.group(1).strip() if m else None
            return "jarvis", (cmd if cmd else None)

        # Test Friday
        if "friday" in clean or "hey friday" in clean:
            m = re.search(r"(?:hey\s+)?friday[,:\s]*(.*)", clean)
            cmd = m.group(1).strip() if m else None
            return "friday", (cmd if cmd else None)

        # Random conversation without wake word -> Strict IGNORE
        logger.info("STANDBY: Ignored speech without wake word: '%s'", text)
        return None

    def _execute_command_pipeline(self, command_text: str, persona: str) -> None:
        """Processes command through ConversationRouter and speaks reply."""
        with self._lock:
            self.state = AssistantState.PROCESSING_COMMAND

        cfg = ConfigManager.load()
        personas_cfg = cfg.get("personas", {})
        persona_key = persona.lower()

        if persona_key == "jarvis":
            j_profile = personas_cfg.get("jarvis", {})
            voice = j_profile.get("voice", "Daniel")
            rate = j_profile.get("speech_rate", 162)
        else:
            f_profile = personas_cfg.get("friday", {})
            voice = f_profile.get("voice", cfg.get("voice", "Moira"))
            rate = f_profile.get("speech_rate", cfg.get("speech_rate", 172))

        logger.info("Processing command: '%s' (Persona: %s, Voice: %s, Rate: %s)", command_text, persona, voice, rate)
        intent, ok, response_text = self.router.route(command_text, persona=persona)
        logger.info("Command result: Intent='%s' | Response='%s'", intent, response_text)

        # Transition to SPEAKING_RESPONSE
        with self._lock:
            self.state = AssistantState.SPEAKING_RESPONSE
            self.mic_service.set_speaking_state(True)

        try:
            self.speech_output.speak(response_text, voice=voice, rate=rate, play_chime=False)
        finally:
            self.mic_service.set_speaking_state(False)
            with self._lock:
                # 11. Return to STANDBY mode automatically
                self.state = AssistantState.STANDBY
                self._active_wake_persona = None
                logger.info("Action complete. Automatically returned to STANDBY mode.")
