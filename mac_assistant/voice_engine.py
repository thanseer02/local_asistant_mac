"""Voice synthesis, persona management, Kokoro TTS pipeline, and prioritized speech queue."""

from dataclasses import dataclass, field
import enum
import logging
import math
import os
import queue
import random
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .kokoro_engine import KokoroEngine
from .text_humanizer import humanize, split_sentences

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
    """
    Handles text humanization, persona voice resolution, and natural Kokoro TTS synthesis.
    Features:
    - Lazy-loaded Kokoro ONNX singleton with automatic fallback to macOS /usr/bin/say.
    - Sentence-level pipelining: plays sentence 1 while concurrently synthesizing sentence 2.
    - Pre-generated audio caching keyed by hash for instant repeating phrase playback.
    - Full barge-in & interruption support: instantly terminates ongoing audio and clears queues.
    - Seamless VRM avatar lip-sync & top-right popup message bubble integration.
    """

    def __init__(self):
        self._last_chosen_greeting: Optional[str] = None
        self._speech_queue: queue.PriorityQueue[SpeechItem] = queue.PriorityQueue()
        self._current_process: Optional[subprocess.Popen] = None
        self._process_lock = threading.Lock()
        self._interrupt_event = threading.Event()
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
        """Returns True if audio playback or speech process is currently active."""
        return self._is_speaking

    def get_active_persona(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves active session persona definition."""
        from .personality import personality_engine
        pid = personality_engine.get_session_persona(config)
        return personality_engine.get_persona(pid)

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
            expired = [k for k, ts in self._recent_utterances.items() if now - ts > self._dedup_window_seconds]
            for k in expired:
                del self._recent_utterances[k]

            if clean in self._recent_utterances:
                return True
            self._recent_utterances[clean] = now
            return False

    def stop_current_speech(self) -> None:
        """Terminates ongoing playback process and signals interruption to the pipeline."""
        self._interrupt_event.set()
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
                item = SpeechItem(
                    priority=int(priority),
                    timestamp=time.time() + 30.0,
                    message=clean_msg,
                    config=dict(config),
                    play_chime=False
                )
                self._speech_queue.put(item)
                return

        # Barge-in: If incoming message is URGENT and speech is active, stop it immediately
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
        """Synchronously speaks farewell before SIGTERM shutdown with hard timeout cap."""
        self.stop_current_speech()
        try:
            while not self._speech_queue.empty():
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
        except Exception:
            pass

        self._execute_speech_pipeline(message, config, play_chime=True, timeout=timeout)

    def _resolve_tts_voice(self, config: Dict[str, Any], persona: Dict[str, Any]) -> Tuple[str, str, float, str]:
        """Resolves engine ('kokoro' | 'say'), voice name, speed, and language."""
        tts_cfg = config.get("tts", {})
        engine = tts_cfg.get("engine", "kokoro").lower()

        pid = persona.get("id", "friday").lower()
        voice_map = tts_cfg.get("persona_voices", {
            "jarvis": "bm_george",
            "friday": "af_heart",
            "alfred": "bm_lewis",
            "coach": "am_adam",
            "zen": "af_sky",
            "noir": "bm_george",
            "sarcastic": "am_michael",
            "pirate": "bm_fable",
            "sleepy": "af_bella"
        })

        kokoro_voice = voice_map.get(pid, "af_heart")
        speed = float(tts_cfg.get("speed", 1.0))
        lang = tts_cfg.get("lang", "en-us")

        return engine, kokoro_voice, speed, lang

    def _execute_speech_pipeline(
        self,
        message: str,
        config: Dict[str, Any],
        play_chime: bool = True,
        timeout: Optional[float] = None
    ) -> None:
        """Coordinates chime, text humanization, avatar animation, and sentence-pipelined speech."""
        if play_chime:
            self.play_hud_chime(config)

        persona = self.get_active_persona(config)
        persona_name = persona.get("name", "Assistant")
        say_voice = persona.get("voice", config.get("voice", "Moira"))
        say_rate = str(persona.get("speech_rate", config.get("speech_rate", 175)))

        engine_choice, kokoro_voice, kokoro_speed, kokoro_lang = self._resolve_tts_voice(config, persona)

        # Humanize text for pure spoken cadence
        spoken_text = humanize(message)
        if not spoken_text:
            return

        sentences = split_sentences(spoken_text)

        logger.info(
            "Speaking with engine '%s' (persona: %s, voice: %s): %s",
            engine_choice, persona_name, kokoro_voice if engine_choice == "kokoro" else say_voice, spoken_text
        )

        from .avatar_client import AvatarClient
        AvatarClient.speaking_start(message=spoken_text, persona=persona_name)

        self._interrupt_event.clear()
        self._is_speaking = True

        # Lip-sync background thread
        stop_lipsync = threading.Event()
        def _lipsync_worker():
            vowels = ["aa", "oh", "ee", "ih", "ou"]
            step = 0
            while not stop_lipsync.is_set():
                amp = 0.35 + 0.55 * math.sin(step * 0.7)
                v = vowels[step % len(vowels)]
                AvatarClient.amplitude(max(0.05, amp), vowel=v)
                step += 1
                time.sleep(0.08)

        lipsync_thread = threading.Thread(target=_lipsync_worker, daemon=True)
        lipsync_thread.start()

        start_time = time.time()

        try:
            kokoro = KokoroEngine.get_instance()
            use_kokoro = (engine_choice == "kokoro") and kokoro.is_model_available()

            if use_kokoro:
                self._play_kokoro_pipelined(
                    sentences=sentences,
                    kokoro=kokoro,
                    voice=kokoro_voice,
                    speed=kokoro_speed,
                    lang=kokoro_lang,
                    say_voice=say_voice,
                    say_rate=say_rate,
                    timeout=timeout,
                    start_time=start_time
                )
            else:
                if engine_choice == "kokoro":
                    logger.warning("Kokoro model files not ready or engine set to say; falling back to /usr/bin/say.")
                self._play_say_fallback(spoken_text, say_voice, say_rate, timeout=timeout)

        except Exception as e:
            logger.error("Unhandled error in speech execution: %s", e)
            # Emergency fallback
            self._play_say_fallback(spoken_text, say_voice, say_rate, timeout=timeout)
        finally:
            stop_lipsync.set()
            with self._process_lock:
                self._current_process = None
            self._is_speaking = False
            AvatarClient.speaking_end()

    def _play_kokoro_pipelined(
        self,
        sentences: List[str],
        kokoro: KokoroEngine,
        voice: str,
        speed: float,
        lang: str,
        say_voice: str,
        say_rate: str,
        timeout: Optional[float],
        start_time: float
    ) -> None:
        """
        Pipelined sentence playback:
        Concurrent worker synthesizes sentence N+1 while sentence N plays through afplay.
        """
        synth_queue: queue.Queue[Optional[Tuple[str, Optional[Path]]]] = queue.Queue(maxsize=3)

        def _synthesize_producer():
            for s in sentences:
                if self._interrupt_event.is_set():
                    break
                wav_path = kokoro.synthesize_to_wav(s, voice=voice, speed=speed, lang=lang)
                synth_queue.put((s, wav_path))
            synth_queue.put(None)  # Sentinel

        producer = threading.Thread(target=_synthesize_producer, daemon=True)
        producer.start()

        while not self._interrupt_event.is_set():
            if timeout and (time.time() - start_time >= timeout):
                logger.warning("Speech exceeded timeout cap (%.1fs). Aborting pipeline.", timeout)
                break

            try:
                item = synth_queue.get(timeout=25.0)
            except queue.Empty:
                logger.warning("Synthesis timeout waiting for next sentence.")
                break

            if item is None:
                break  # All sentences complete

            sentence_text, wav_path = item

            if self._interrupt_event.is_set():
                break

            if wav_path and wav_path.exists():
                self._play_afplay(wav_path, timeout=timeout)
            else:
                logger.warning("Kokoro synthesis returned None for '%s'. Falling back to say for this chunk.", sentence_text)
                self._play_say_fallback(sentence_text, say_voice, say_rate, timeout=timeout)

    def _play_afplay(self, wav_path: Path, timeout: Optional[float] = None) -> None:
        """Plays audio file using macOS native afplay binary."""
        try:
            proc = subprocess.Popen(["/usr/bin/afplay", str(wav_path.resolve())])
            with self._process_lock:
                self._current_process = proc

            if timeout:
                proc.wait(timeout=timeout)
            else:
                proc.wait()
        except subprocess.TimeoutExpired:
            proc.terminate()
        except Exception as e:
            logger.debug("afplay execution error: %s", e)
        finally:
            with self._process_lock:
                if self._current_process == proc:
                    self._current_process = None

    def _play_say_fallback(self, text: str, voice: str, rate: str, timeout: Optional[float] = None) -> None:
        """Fallback synthesis using native macOS /usr/bin/say."""
        try:
            proc = subprocess.Popen(["/usr/bin/say", "-v", voice, "-r", rate, text])
            with self._process_lock:
                self._current_process = proc

            if timeout:
                proc.wait(timeout=timeout)
            else:
                proc.wait()
        except subprocess.TimeoutExpired:
            proc.terminate()
        except Exception as e:
            logger.error("Error executing /usr/bin/say fallback: %s", e)
        finally:
            with self._process_lock:
                if self._current_process == proc:
                    self._current_process = None

    def _execute_say(
        self,
        message: str,
        config: Dict[str, Any],
        play_chime: bool = True,
        timeout: Optional[float] = None
    ) -> None:
        """Compatibility wrapper forwarding to the unified speech pipeline."""
        self._execute_speech_pipeline(message, config, play_chime=play_chime, timeout=timeout)

    def _speech_worker(self) -> None:
        """Background worker consuming queued speech by priority."""
        while self._running:
            try:
                item = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            now = time.time()
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
