"""Strict wake-word state manager implementing STANDBY -> WAKE_WORD_DETECTED -> LISTENING -> PROCESSING -> SPEAKING -> FOLLOW_UP."""

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
    FOLLOW_UP = "FOLLOW_UP"


class StrictVoiceController:
    """Manages strict wake-word activation workflow with follow-up mode and barge-in:

    1. STANDBY mode: offline wake detection (openWakeWord / acoustic detector).
    2. WAKE_WORD_DETECTED: Triggers short activation chime ('hud_chime.wav').
    3. LISTENING_FOR_COMMAND: Captures command utterance with silence timeout.
    4. PROCESSING_COMMAND: Transcribes with Whisper, executes tool/chat.
    5. SPEAKING_RESPONSE: Speaks output via speech engine.
    6. FOLLOW_UP mode: Listens for ~8 seconds without requiring the wake word again.
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

        # Core Engines (Lazy or initialized)
        self.wake_detector = WakeWordService(
            jarvis_threshold=float(voice_cfg.get("wake_sensitivity", 0.5)),
            friday_threshold=float(voice_cfg.get("wake_sensitivity", 0.5))
        )
        self.mic_service = MicrophoneService(
            speech_threshold=self.speech_threshold,
            silence_duration=self.command_silence_duration
        )
        self._recognizer: Optional[SpeechRecognitionService] = None
        self.router = ConversationRouter()

        # Follow-up and timers
        self._active_wake_persona: Optional[str] = None
        self._listening_timeout_timer: Optional[threading.Timer] = None
        self._followup_timer: Optional[threading.Timer] = None

    @property
    def recognizer(self) -> SpeechRecognitionService:
        if self._recognizer is None:
            self._recognizer = SpeechRecognitionService()
        return self._recognizer

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
            success = self.mic_service.start_listening(
                on_speech_chunk=self._on_audio_chunk,
                device_index=device_idx
            )
            if success:
                logger.info("Assistant started in STANDBY mode. Listening strictly for 'Friday' or 'Jarvis'.")
            return success

    def _cancel_timers(self) -> None:
        """Cancels any pending idle or follow-up timers."""
        if self._listening_timeout_timer:
            try:
                self._listening_timeout_timer.cancel()
            except Exception:
                pass
            self._listening_timeout_timer = None

        if self._followup_timer:
            try:
                self._followup_timer.cancel()
            except Exception:
                pass
            self._followup_timer = None

    def _on_listening_timeout(self) -> None:
        with self._lock:
            if self.state in [AssistantState.LISTENING_FOR_COMMAND, AssistantState.FOLLOW_UP]:
                logger.info("No command received within window. Returning to STANDBY mode.")
                self.state = AssistantState.STANDBY
                self._active_wake_persona = None

    def stop(self) -> None:
        self._cancel_timers()
        with self._lock:
            if not self._running:
                return
            self._running = False
            self.state = AssistantState.STANDBY
            self.mic_service.stop_listening()
            logger.info("StrictVoiceController stopped.")

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        """Invoked on each captured speech chunk from the microphone."""
        # Barge-in support: If speaking and wake word detected, stop speech
        if self.state == AssistantState.SPEAKING_RESPONSE or self.mic_service._is_speaking:
            detected_wake = self._detect_wake_word_in_audio(audio_bytes)
            if detected_wake:
                logger.info("Barge-in detected during speech! Stopping speech...")
                self.speech_output.stop_speaking()
                with self._lock:
                    self.state = AssistantState.WAKE_WORD_DETECTED
                    self._active_wake_persona = detected_wake[0]
                self.speech_output.play_hud_chime("hud_chime.wav")
                return
            return

        # 1. FOLLOW_UP MODE: Can accept direct commands without wake word
        if self.state == AssistantState.FOLLOW_UP:
            self._cancel_timers()
            with self._lock:
                self.state = AssistantState.PROCESSING_COMMAND

            command_text = self.recognizer.transcribe_audio_bytes(audio_bytes)
            if command_text and len(command_text.strip()) >= 2:
                persona = self._active_wake_persona or self.config.get("assistant_persona", "friday")
                self._execute_command_pipeline(command_text, persona=persona)
                return
            else:
                with self._lock:
                    self.state = AssistantState.STANDBY
                return

        # 2. STANDBY MODE: Only wake words ('Friday' or 'Jarvis') can transition state
        if self.state == AssistantState.STANDBY:
            detected_wake = self._detect_wake_word_in_audio(audio_bytes)
            if not detected_wake:
                logger.debug("STANDBY: Audio ignored (no wake word detected).")
                return

            wake_word, immediate_command = detected_wake
            logger.info("Wake word detected: '%s' (Immediate command: '%s')", wake_word, immediate_command)

            with self._lock:
                self.state = AssistantState.WAKE_WORD_DETECTED
                self._active_wake_persona = wake_word

            self.speech_output.play_hud_chime("hud_chime.wav")

            if immediate_command:
                self._execute_command_pipeline(immediate_command, persona=wake_word)
            else:
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
                    logger.info("Transitioned to LISTENING_FOR_COMMAND. Awaiting instruction (5s timeout)...")
                    self._cancel_timers()
                    self._listening_timeout_timer = threading.Timer(5.0, self._on_listening_timeout)
                    self._listening_timeout_timer.daemon = True
                    self._listening_timeout_timer.start()

            return

        # 3. LISTENING_FOR_COMMAND MODE: Capture user instruction
        if self.state == AssistantState.LISTENING_FOR_COMMAND:
            self._cancel_timers()
            with self._lock:
                self.state = AssistantState.PROCESSING_COMMAND

            logger.info("Transcribing captured command with Whisper...")
            command_text = self.recognizer.transcribe_audio_bytes(audio_bytes)

            if not command_text or len(command_text.strip()) < 2:
                logger.info("No clear command transcribed. Returning to STANDBY.")
                self.state = AssistantState.STANDBY
                return

            persona = self._active_wake_persona or self.config.get("assistant_persona", "friday")
            self._execute_command_pipeline(command_text, persona=persona)

    def _detect_wake_word_in_audio(self, audio_bytes: bytes) -> Optional[Tuple[str, Optional[str]]]:
        """Strictly tests audio chunk for 'Friday' or 'Jarvis' using openWakeWord then Whisper."""
        try:
            samples = np.frombuffer(audio_bytes, dtype=np.int16)
            if len(samples) >= 1280:
                frame = samples[-1280:]
                oww_result = self.wake_detector.process_frame(frame)
                if oww_result == "jarvis":
                    return "jarvis", None
        except Exception:
            pass

        text = self.recognizer.transcribe_audio_bytes(audio_bytes)
        if not text:
            return None

        clean = text.lower().strip(",.!? ")

        # Test Jarvis
        jarvis_match = re.search(r"(?:hey\s+|hi\s+|ok\s+|okay\s+)?\b(jarvis|jarvir|darius|travis|charvis|service|harvest|drivers|jarv|jarve)\b[,:\s]*(.*)", clean)
        if not jarvis_match and ("jarv" in clean or "darius" in clean or "travis" in clean):
            m = re.search(r"(?:hey\s+|hi\s+|ok\s+|okay\s+)?([a-z]*jarv[a-z]*|[a-z]*darius[a-z]*)[,:\s]*(.*)", clean)
            if m:
                jarvis_match = m
        if jarvis_match:
            cmd = jarvis_match.group(2).strip()
            return "jarvis", (cmd if cmd else None)

        # Test Friday
        friday_match = re.search(r"(?:hey\s+|hi\s+|ok\s+|okay\s+)?\b(friday|freida|frida|fry\s*day)\b[,:\s]*(.*)", clean)
        if friday_match:
            cmd = friday_match.group(2).strip()
            return "friday", (cmd if cmd else None)

        logger.info("STANDBY: Ignored speech without wake word: '%s'", text)
        return None

    def _execute_command_pipeline(self, command_text: str, persona: str) -> None:
        """Processes command through ConversationRouter, speaks reply, and enters follow-up mode."""
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

        logger.info("Processing command: '%s' (Persona: %s)", command_text, persona)
        intent, ok, response_text = self.router.route(command_text, persona=persona)
        logger.info("Command result: Intent='%s' | Response='%s'", intent, response_text)

        # Stop command check
        if intent == "stop":
            with self._lock:
                self.state = AssistantState.STANDBY
                self._active_wake_persona = None
            return

        with self._lock:
            self.state = AssistantState.SPEAKING_RESPONSE
            self.mic_service.set_speaking_state(True)

        try:
            if response_text:
                self.speech_output.speak(response_text, voice=voice, rate=rate, play_chime=False)
        finally:
            self.mic_service.set_speaking_state(False)
            with self._lock:
                # Transition to FOLLOW_UP mode for ~8 seconds
                self.state = AssistantState.FOLLOW_UP
                logger.info("Entered FOLLOW_UP mode (listening for 8s without wake word)...")
                self._cancel_timers()
                self._followup_timer = threading.Timer(8.0, self._on_listening_timeout)
                self._followup_timer.daemon = True
                self._followup_timer.start()
