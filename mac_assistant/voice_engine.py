"""Prioritized, thread-safe speech output engine wrapping macOS /usr/bin/say & afplay.

Supports:
- Priority queue: URGENT (1) > BRIEFING (2) > REMINDER (3) > NORMAL (4)
- Barge-in & interruption (stops ongoing playback immediately)
- Stop / quiet commands
- Native macOS /usr/bin/say with Daniel (Jarvis) and Moira (Friday)
"""

from dataclasses import dataclass, field
import enum
import logging
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.VoiceEngine")

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"


class SpeechPriority(enum.IntEnum):
    URGENT = 1     # System alarms, direct user voice answers, shutdown farewells
    BRIEFING = 2   # Morning briefing, git reports
    REMINDER = 3   # 20-20-20, hydration, scheduled tea/lunch
    NORMAL = 4     # Low-priority background feedback


@dataclass(order=True)
class SpeechTask:
    priority: int
    timestamp: float = field(compare=False)
    message: str = field(compare=False)
    config: Dict[str, Any] = field(compare=False)
    play_chime: bool = field(default=True, compare=False)


class VoiceEngine:
    """Handles text formatting, persona management, HUD chimes, and prioritized speech synthesis."""

    def __init__(self):
        self._last_chosen_greeting: Optional[str] = None
        self._speech_queue: queue.PriorityQueue[SpeechTask] = queue.PriorityQueue()
        self._current_process: Optional[subprocess.Popen] = None
        self._process_lock = threading.Lock()
        self._running = True
        self._is_speaking = False
        self._worker_thread = threading.Thread(
            target=self._speech_worker, name="MacAssistant-SpeechWorker", daemon=True
        )
        self._worker_thread.start()

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def stop_speaking(self) -> None:
        """Immediately interrupts any current speech or chime audio (barge-in)."""
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
        # Drain non-urgent items from queue
        self._drain_queue()
        self._is_speaking = False
        logger.info("Speech playback interrupted (barge-in / stop requested).")

    def _drain_queue(self) -> None:
        """Clears remaining queued speech tasks."""
        try:
            while not self._speech_queue.empty():
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
        except queue.Empty:
            pass

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

    def get_greeting(self, config: Dict[str, Any], hour: Optional[int] = None) -> str:
        """Constructs a time-aware, non-repeating greeting tailored to the persona."""
        import random
        from datetime import datetime
        if hour is None:
            hour = datetime.now().hour

        persona = self.get_active_persona(config)
        name = config.get("user_name", "Sir")
        greetings = persona.get("greetings", {})

        if 5 <= hour < 12:
            pool = greetings.get("morning", ["Good morning, {name}!"])
        elif 12 <= hour < 17:
            pool = greetings.get("afternoon", ["Good afternoon, {name}!"])
        elif 17 <= hour < 21:
            pool = greetings.get("evening", ["Good evening, {name}!"])
        else:
            pool = greetings.get("night", ["Working late, {name}?"])

        if isinstance(pool, list) and pool:
            candidates = [g for g in pool if g != self._last_chosen_greeting] or pool
            chosen = random.choice(candidates)
            self._last_chosen_greeting = chosen
            return chosen.format(name=name, title=name)
        elif isinstance(pool, str):
            return pool.format(name=name, title=name)

        return f"Welcome back, {name}!"

    def get_goodbye(self, config: Dict[str, Any]) -> str:
        """Constructs a polite shutdown/farewell message tailored to the persona."""
        import random
        persona = self.get_active_persona(config)
        name = config.get("user_name", "Sir")
        goodbyes = persona.get("goodbyes", [])

        if isinstance(goodbyes, list) and goodbyes:
            return random.choice(goodbyes).format(name=name, title=name)
        elif isinstance(goodbyes, str):
            return goodbyes.format(name=name, title=name)

        return f"Goodbye, {name}. Have a restful evening."

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

    def speak(
        self,
        message: str,
        config: Dict[str, Any],
        priority: str = "normal",
        play_chime: bool = True
    ) -> None:
        """Enqueues text to be spoken with priority.

        priority can be: 'urgent', 'briefing', 'reminder', 'normal'
        """
        if not message or not message.strip():
            return

        prio_map = {
            "urgent": SpeechPriority.URGENT,
            "briefing": SpeechPriority.BRIEFING,
            "reminder": SpeechPriority.REMINDER,
            "normal": SpeechPriority.NORMAL,
        }
        num_prio = prio_map.get(priority.lower(), SpeechPriority.NORMAL)

        # If urgent message arrives while lower priority is speaking, interrupt it
        if num_prio == SpeechPriority.URGENT and self._is_speaking:
            with self._process_lock:
                if self._current_process and self._current_process.poll() is None:
                    try:
                        self._current_process.terminate()
                    except Exception:
                        pass

        task = SpeechTask(
            priority=int(num_prio),
            timestamp=time.time(),
            message=message.strip(),
            config=dict(config),
            play_chime=play_chime
        )
        self._speech_queue.put(task)

    def speak_sync(self, message: str, config: Dict[str, Any], play_chime: bool = True) -> None:
        """Synchronously speaks without queuing (used for shutdown farewell)."""
        self.stop_speaking()
        self._execute_speech(message, config, play_chime=play_chime)

    def _execute_speech(self, message: str, config: Dict[str, Any], play_chime: bool = True) -> None:
        """Executes actual playback using /usr/bin/say."""
        if play_chime:
            self.play_hud_chime(config)

        persona = self.get_active_persona(config)
        voice = persona.get("voice", config.get("voice", "Moira"))
        rate = str(persona.get("speech_rate", config.get("speech_rate", 168)))

        # Clean speakable text (remove markdown symbols)
        clean_text = message.replace("*", "").replace("#", "").replace("`", "").strip()

        try:
            self._is_speaking = True
            proc = subprocess.Popen(["/usr/bin/say", "-v", voice, "-r", rate, clean_text])
            with self._process_lock:
                self._current_process = proc
            proc.wait()
        except Exception as e:
            logger.error("Error executing speech synthesis: %s", e)
        finally:
            with self._process_lock:
                self._current_process = None
            self._is_speaking = False

    def _speech_worker(self) -> None:
        """Worker thread processing items sequentially from priority queue."""
        while self._running:
            try:
                task = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._execute_speech(task.message, task.config, play_chime=task.play_chime)
            except Exception as e:
                logger.error("Unhandled error in speech worker: %s", e)
            finally:
                self._speech_queue.task_done()
