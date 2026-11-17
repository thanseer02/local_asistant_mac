"""Non-blocking audio output player supporting immediate interruption (barge-in)."""

import collections
import queue
import threading
import time
from typing import Optional

import pyaudio
from modules.services.logging_service import logger


class AudioOutputService:
    """
    Plays 24,000 Hz, 16-bit Mono PCM audio chunks streamed from OpenAI Realtime API.
    Supports instant flushing / clearing when the user interrupts (barge-in).
    """

    def __init__(
        self,
        sample_rate: int = 24000,
        chunk_size: int = 1024,
        device_index: Optional[int] = None
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.device_index = device_index

        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._is_playing = False

    @property
    def is_playing(self) -> bool:
        return self._is_playing or not self._audio_queue.empty()

    def start(self) -> bool:
        """Starts background audio playback worker."""
        with self._lock:
            if self._running:
                return True

            self._pyaudio = pyaudio.PyAudio()

            # Auto-resolve output device if None
            if self.device_index is None:
                self.device_index = self._find_best_output_device(self._pyaudio)

            try:
                self._stream = self._pyaudio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=self.device_index,
                    frames_per_buffer=self.chunk_size
                )
            except Exception as e:
                logger.warning(f"Failed opening output at {self.sample_rate} Hz (device={self.device_index}): {e}")
                # Try hardware native rate fallback
                try:
                    dev_info = self._pyaudio.get_device_info_by_index(self.device_index) if self.device_index is not None else {}
                    native_rate = int(dev_info.get("defaultSampleRate", 24000))
                    logger.info(f"Retrying audio output at native rate: {native_rate} Hz...")
                    self.sample_rate = native_rate
                    self._stream = self._pyaudio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=self.sample_rate,
                        output=True,
                        output_device_index=self.device_index,
                        frames_per_buffer=self.chunk_size
                    )
                except Exception as retry_err:
                    logger.error(f"Failed opening audio output on retry: {retry_err}")
                    if self._pyaudio:
                        self._pyaudio.terminate()
                        self._pyaudio = None
                    return False

            self._running = True
            self._thread = threading.Thread(
                target=self._play_loop,
                name="Realtime-AudioPlayer",
                daemon=True
            )
            self._thread.start()
            logger.info(f"Audio output initialized at {self.sample_rate} Hz.")
            return True

    def enqueue_chunk(self, chunk: bytes) -> None:
        """Appends raw PCM audio chunk to playback buffer."""
        if self._running and chunk:
            self._audio_queue.put(chunk)

    def interrupt(self) -> None:
        """
        Barge-in: Immediately flushes pending audio chunks and truncates speaker output.
        Called as soon as user starts speaking or speech_started event arrives.
        """
        cleared_chunks = 0
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
                cleared_chunks += 1
            except queue.Empty:
                break
        self._is_playing = False
        if cleared_chunks > 0:
            logger.info(f"Barge-in triggered: flushed {cleared_chunks} audio chunks from playback queue.")

    def stop(self) -> None:
        """Stops audio player and releases PyAudio stream."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        self.interrupt()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

            if self._pyaudio:
                try:
                    self._pyaudio.terminate()
                except Exception:
                    pass
                self._pyaudio = None

        logger.info("Audio output player stopped.")

    def _find_best_output_device(self, p: pyaudio.PyAudio) -> Optional[int]:
        """Discovers best available output device (Headset, Speakers, etc.)."""
        count = p.get_device_count()
        candidates = []
        for i in range(count):
            try:
                info = p.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0:
                    candidates.append((i, info.get("name", "")))
            except Exception:
                continue

        # Prioritize Bluetooth headset (WH-CH510, AirPods)
        for idx, name in candidates:
            if any(k in name.lower() for k in ["wh-ch", "sony", "airpod", "headset", "bluetooth"]):
                return idx

        # Fallback to Mac speakers
        for idx, name in candidates:
            if "speaker" in name.lower():
                return idx

        return candidates[0][0] if candidates else None

    def _play_loop(self) -> None:
        """Continuously pulls PCM chunks from queue and writes to speaker."""
        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.05)
            except queue.Empty:
                self._is_playing = False
                continue

            self._is_playing = True
            try:
                if self._stream and self._running:
                    self._stream.write(chunk)
            except Exception as e:
                logger.debug(f"Error writing to audio output: {e}")
                time.sleep(0.01)
