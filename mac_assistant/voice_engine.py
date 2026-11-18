"""Voice synthesis, Marvel persona management, and prioritized speech queue."""

from dataclasses import dataclass, field
import enum
import logging
import os
import queue
import random
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.VoiceEngine")

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class SpeechPriority(enum.IntEnum):
    """Speech priority hierarchy. Lower integer value = higher priority."""
    URGENT = 1     # Shutdown farewell, emergency alarms (barges in immediately)
    BRIEFING = 2   # Morning briefing, agenda, unlock greetings
    REMINDER = 3   # 20-20-20, hydration, scheduled meal/tea alerts (drops if >60s stale)
    NORMAL = 4     # Low-priority feedback


@dataclass(order=True)
class SpeechItem:
    """Queued speech request."""
    priority: int
    timestamp: float = field(compare=False)
    message: str = field(compare=False)
    config: Dict[str, Any] = field(compare=False)
    play_chime: bool = field(default=True, compare=False)


class VoiceEngine:
    """Handles text formatting, persona management, and prioritized macOS speech synthesis."""

    def __init__(self):
        self._last_chosen_greeting: Optional[str] = None
        self._speech_queue: queue.PriorityQueue[SpeechItem] = queue.PriorityQueue()
        self._current_process: Optional[subprocess.Popen] = None
        self._process_lock = threading.Lock()
        self._running = True
        self._is_speaking = False

        # Duplicate suppression window
        self._recent_utterances: Dict[str, float] = {}
        self._recent_lock = threading.Lock()
        self._dedup_window_seconds = 5.0

        # Background speech worker thread
        self._worker_thread = threading.Thread(
            target=self._speech_worker,
            name="MacAssistant-SpeechWorker",
            daemon=True
        )
        self._worker_thread.start()

    @property
    def is_speaking(self) -> bool:
        """Returns True if audio playback or say process is currently active."""
        return self._is_speaking

    def get_active_persona(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves the active persona ('friday' or 'jarvis') from configuration."""
        persona_key = config.get("assistant_persona", "friday").lower()
        personas = config.get("personas", {})
        if persona_key in personas:
            return personas[persona_key]
        return {
            "voice": config.get("voice", "Moira"),
            "speech_rate": config.get("speech_rate", 175),
            "greetings": {}
        }

    def get_greeting(self, config: Dict[str, Any], hour: Optional[int] = None, context: Optional[Dict[str, Any]] = None) -> str:
        """Constructs a time-aware, non-repeating, personality-driven greeting."""
        from .personality import personality_engine
        ctx = dict(context or {})
        ctx["name"] = config.get("user_name", "Sir")
        msg, rate = personality_engine.pick("unlock_greeting", context=ctx, config=config)
        return msg

    def get_goodbye(self, config: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        """Constructs a polite, non-repeating shutdown/farewell message tailored to the persona."""
        from .personality import personality_engine
        ctx = dict(context or {})
        ctx["name"] = config.get("user_name", "Sir")
        msg, rate = personality_engine.pick("shutdown", context=ctx, config=config)
        return msg

    def play_hud_chime(self, config: Dict[str, Any]) -> None:
        """Plays the Marvel HUD chime sound effect before speaking if enabled."""
        sound_cfg = config.get("hud_sound", {})
        if not sound_cfg.get("enabled", True):
            return

        sound_file = sound_cfg.get("sound_file", "hud_chime.wav")
        sound_path = SOUNDS_DIR / sound_file
        if sound_path.exists():
            try:
                proc = subprocess.Popen(["/usr/bin/afplay", str(sound_path)])
                with self._process_lock:
                    self._current_process = proc
                proc.wait(timeout=2.0)
            except Exception as e:
                logger.debug("HUD chime audio playback error: %s", e)
            finally:
                with self._process_lock:
                    if self._current_process == proc:
                        self._current_process = None

    def _is_duplicate(self, text: str) -> bool:
        """Checks if identical text was submitted within dedup window."""
        now = time.time()
        clean = text.strip().lower()
        with self._recent_lock:
            # Purge expired
            expired = [k for k, ts in self._recent_utterances.items() if now - ts > self._dedup_window_seconds]
            for k in expired:
                del self._recent_utterances[k]

            if clean in self._recent_utterances:
                return True
            self._recent_utterances[clean] = now
            return False

    def stop_current_speech(self) -> None:
        """Terminates ongoing afplay or say process to allow barge-in."""
        with self._process_lock:
            if self._current_process and self._current_process.poll() is None:
                try:
                    self._current_process.terminate()
                    self._current_process.wait(timeout=0.3)
                except Exception:
                    try:
                        self._current_process.kill()
                    except Exception:
                        pass
                self._current_process = None
        self._is_speaking = False

    def speak(
        self,
        message: str,
        config: Dict[str, Any],
        priority: SpeechPriority = SpeechPriority.NORMAL,
        play_chime: bool = True
    ) -> None:
        """Enqueues speech with priority. URGENT interrupts active lower-priority speech."""
        if not message or not message.strip():
            return

        clean_msg = message.strip()

        # Check Focus / Meeting suppression for non-urgent speech
        from .focus_guard import FocusGuard
        if priority in (SpeechPriority.REMINDER, SpeechPriority.NORMAL):
            if FocusGuard.is_busy(config):
                logger.info("FocusGuard: User is in a meeting or Focus mode. Deferring speech: '%s'", clean_msg)
                # Re-queue once with a 60-second delay; if already deferred once, it will be dropped if stale
                item = SpeechItem(
                    priority=int(priority),
                    timestamp=time.time() + 30.0,
                    message=clean_msg,
                    config=dict(config),
                    play_chime=False
                )
                self._speech_queue.put(item)
                return

        # Barge-in: If incoming message is URGENT and something is currently speaking, terminate it
        if priority == SpeechPriority.URGENT and self._is_speaking:
            logger.info("URGENT priority barge-in requested. Interrupting current speech...")
            self.stop_current_speech()

        item = SpeechItem(
            priority=int(priority),
            timestamp=time.time(),
            message=clean_msg,
            config=dict(config),
            play_chime=play_chime
        )
        self._speech_queue.put(item)

    def speak_farewell_and_wait(self, message: str, config: Dict[str, Any], timeout: float = 3.0) -> None:
        """Synchronously speaks urgent farewell before SIGTERM shutdown with hard timeout cap."""
        self.stop_current_speech()
        # Drain non-urgent pending items
        try:
            while not self._speech_queue.empty():
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
        except Exception:
            pass

        self._execute_say(message, config, play_chime=True, timeout=timeout)

    def _execute_say(
        self,
        message: str,
        config: Dict[str, Any],
        play_chime: bool = True,
        timeout: Optional[float] = None
    ) -> None:
        """Executes HUD chime and /usr/bin/say synthesis."""
        if play_chime:
            self.play_hud_chime(config)

        persona = self.get_active_persona(config)
        voice = persona.get("voice", config.get("voice", "Moira"))
        rate = str(persona.get("speech_rate", config.get("speech_rate", 175)))

        logger.info("Speaking with voice '%s' (rate %s): %s", voice, rate, message)

        try:
            self._is_speaking = True
            proc = subprocess.Popen(["/usr/bin/say", "-v", voice, "-r", rate, message])
            with self._process_lock:
                self._current_process = proc

            if timeout:
                proc.wait(timeout=timeout)
            else:
                proc.wait()
        except subprocess.TimeoutExpired:
            logger.warning("Speech process exceeded timeout (%.1fs). Terminating.", timeout)
            proc.terminate()
        except Exception as e:
            logger.error("Error executing /usr/bin/say: %s", e)
        finally:
            with self._process_lock:
                if self._current_process == proc:
                    self._current_process = None
            self._is_speaking = False

    def _speech_worker(self) -> None:
        """Background worker consuming queued speech by priority."""
        while self._running:
            try:
                item = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            now = time.time()
            # Stale check: Drop REMINDER messages older than 60 seconds
            if item.priority == int(SpeechPriority.REMINDER) and (now - item.timestamp > 60.0):
                logger.info("Dropping stale reminder speech (>60s old): '%s'", item.message)
                self._speech_queue.task_done()
                continue

            try:
                self._execute_say(item.message, item.config, play_chime=item.play_chime)
            except Exception as e:
                logger.error("Unhandled error in speech worker loop: %s", e)
            finally:
                self._speech_queue.task_done()
