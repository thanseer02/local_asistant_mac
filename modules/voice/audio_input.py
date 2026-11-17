"""Audio input capture service streaming 24kHz/16-bit PCM chunks asynchronously."""

import asyncio
import collections
import math
import struct
import threading
import time
from typing import Callable, Optional

import pyaudio
from modules.services.logging_service import logger


class AudioInputService:
    """
    Manages non-blocking audio capture from microphone.
    Streams 24,000 Hz, 16-bit Mono PCM audio chunks matching OpenAI Realtime requirements.
    Supports mute flags and real-time energy monitoring.
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
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._is_muted = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_muted(self, muted: bool) -> None:
        """Temporarily mutes microphone streaming."""
        self._is_muted = muted

    def start(self, on_audio_chunk: Callable[[bytes], None], loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        """Starts background microphone stream."""
        with self._lock:
            if self._running:
                return True

            self._loop = loop
            self._pyaudio = pyaudio.PyAudio()

            # Device auto-discovery if not explicitly specified
            if self.device_index is None:
                self.device_index = self._find_best_input_device(self._pyaudio)

            try:
                self._stream = self._pyaudio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.device_index,
                    frames_per_buffer=self.chunk_size
                )
            except Exception as e:
                logger.error(f"Failed to open microphone (device={self.device_index}, rate={self.sample_rate}): {e}")
                # Fallback attempt at 16000 if 24000 is not supported natively by hardware
                if self.sample_rate != 16000:
                    try:
                        logger.info("Attempting fallback to 16000 Hz...")
                        self.sample_rate = 16000
                        self._stream = self._pyaudio.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=self.sample_rate,
                            input=True,
                            input_device_index=self.device_index,
                            frames_per_buffer=self.chunk_size
                        )
                    except Exception as fallback_err:
                        logger.error(f"Fallback audio open failed: {fallback_err}")
                        self._cleanup()
                        return False
                else:
                    self._cleanup()
                    return False

            self._running = True
            self._thread = threading.Thread(
                target=self._read_loop,
                args=(on_audio_chunk,),
                name="Realtime-MicReader",
                daemon=True
            )
            self._thread.start()
            logger.info(f"Microphone capturing on device [{self.device_index}] at {self.sample_rate} Hz.")
            return True

    def stop(self) -> None:
        """Halts microphone streaming."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        self._cleanup()
        logger.info("Microphone capture stopped.")

    def _cleanup(self) -> None:
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

    def _find_best_input_device(self, p: pyaudio.PyAudio) -> Optional[int]:
        """Discovers best available input device (Bluetooth headset, USB, etc.)."""
        count = p.get_device_count()
        candidates = []
        for i in range(count):
            try:
                info = p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    name = info.get("name", "")
                    candidates.append((i, name))
            except Exception:
                continue

        # Look for WH-CH510, AirPods, or Bluetooth
        for idx, name in candidates:
            if any(k in name.lower() for k in ["wh-ch", "sony", "airpod", "headset", "bluetooth", "usb"]):
                return idx

        return candidates[0][0] if candidates else None

    def _read_loop(self, callback: Callable[[bytes], None]) -> None:
        """Reads audio frames continuously and passes them to callback."""
        while self._running:
            try:
                data = self._stream.read(self.chunk_size, exception_on_overflow=False)
            except Exception as e:
                time.sleep(0.02)
                continue

            if self._is_muted or not data:
                continue

            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error in audio input callback: {e}")
