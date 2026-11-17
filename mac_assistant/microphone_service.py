"""Microphone capture service with adaptive energy profiling, silence detection, and thread-safe streaming."""

import collections
import logging
import math
import struct
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("MacAssistant.MicrophoneService")


class MicrophoneService:
    """
    Thread-safe microphone capture service.
    Implements dynamic silence detection and speech chunk capture.
    """

    def __init__(
        self,
        rate: int = 16000,
        chunk_size: int = 1024,
        speech_threshold: float = 400.0,
        silence_duration: float = 1.2
    ):
        self.rate = rate
        self.chunk_size = chunk_size
        self.speech_threshold = speech_threshold
        self.silence_duration = silence_duration

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stream = None
        self._pyaudio_instance = None
        self._is_speaking = False  # Set to True while assistant speaks to prevent mic feedback

    def set_speaking_state(self, is_speaking: bool) -> None:
        """Mutes mic processing while the Mac is speaking to prevent feedback loops."""
        self._is_speaking = is_speaking

    def start_listening(
        self,
        on_speech_chunk: Callable[[bytes], None],
        device_index: Optional[int] = None
    ) -> bool:
        """Starts background audio capture thread."""
        with self._lock:
            if self._running:
                logger.warning("MicrophoneService is already running.")
                return True

            try:
                import pyaudio
            except ImportError:
                logger.error("pyaudio is required for MicrophoneService.")
                return False

            self._pyaudio_instance = pyaudio.PyAudio()

            # Auto-resolve device if none provided
            if device_index is None:
                device_index, self.rate = self._resolve_input_device(self._pyaudio_instance)

            if device_index is None:
                logger.warning("No functional audio input device available.")
                self._pyaudio_instance.terminate()
                self._pyaudio_instance = None
                return False

            try:
                self._stream = self._pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk_size
                )
            except Exception as e:
                logger.error("Failed opening microphone stream on device %s: %s", device_index, e)
                self._pyaudio_instance.terminate()
                self._pyaudio_instance = None
                return False

            self._running = True
            self._thread = threading.Thread(
                target=self._capture_loop,
                args=(on_speech_chunk,),
                name="MacAssistant-MicWorker",
                daemon=True
            )
            self._thread.start()
            logger.info("Microphone service started on device [%d] at %d Hz.", device_index, self.rate)
            return True

    def stop_listening(self) -> None:
        """Gracefully halts microphone capture and releases audio resources."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

            if self._pyaudio_instance:
                try:
                    self._pyaudio_instance.terminate()
                except Exception:
                    pass
                self._pyaudio_instance = None

        logger.info("Microphone service stopped.")

    def _resolve_input_device(self, p) -> tuple:
        """Discovers best available microphone (Bluetooth, USB, or Default)."""
        count = p.get_device_count()
        candidates = []

        for i in range(count):
            try:
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    rate = int(info.get("defaultSampleRate", 16000))
                    candidates.append((i, info["name"], rate))
            except Exception:
                continue

        # Prioritize headsets (WH-CH510, AirPods, etc.)
        for idx, name, rate in candidates:
            if any(k in name.lower() for k in ["wh-ch", "sony", "airpod", "headset", "bluetooth", "usb"]):
                return idx, rate

        if candidates:
            return candidates[0][0], candidates[0][2]

        return None, 16000

    def _capture_loop(self, on_speech_chunk: Callable[[bytes], None]) -> None:
        """Worker loop reading frames, detecting speech starts and trailing silence."""
        audio_buffer = []
        is_speech_active = False
        silence_start_time = None
        pre_roll_buffer = collections.deque(maxlen=4)  # Preserve ~250ms before trigger

        while self._running:
            try:
                data = self._stream.read(self.chunk_size, exception_on_overflow=False)
            except Exception as e:
                logger.debug("Mic read error: %s", e)
                time.sleep(0.05)
                continue

            # Skip audio processing while assistant is speaking (anti-loop guard)
            if self._is_speaking:
                time.sleep(0.05)
                continue

            shorts = struct.unpack(f"{self.chunk_size}h", data)
            sum_squares = sum(s * s for s in shorts)
            rms = math.sqrt(sum_squares / self.chunk_size)

            if rms >= self.speech_threshold:
                if not is_speech_active:
                    is_speech_active = True
                    audio_buffer = list(pre_roll_buffer)
                    logger.debug("Speech start detected (RMS: %.0f)", rms)
                audio_buffer.append(data)
                silence_start_time = None
            else:
                if is_speech_active:
                    audio_buffer.append(data)
                    now = time.time()
                    if silence_start_time is None:
                        silence_start_time = now
                    elif now - silence_start_time >= self.silence_duration:
                        # End of utterance reached
                        logger.debug("End of utterance detected. Dispatching %d audio chunks.", len(audio_buffer))
                        complete_utterance = b"".join(audio_buffer)
                        audio_buffer.clear()
                        is_speech_active = False
                        silence_start_time = None
                        try:
                            on_speech_chunk(complete_utterance)
                        except Exception as cb_err:
                            logger.error("Error in on_speech_chunk callback: %s", cb_err)
                else:
                    pre_roll_buffer.append(data)
