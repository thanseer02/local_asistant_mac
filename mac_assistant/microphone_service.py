"""Microphone capture service with device pinning, native sample rate capture, and anti-ducking."""

import collections
import logging
import math
import struct
import threading
import time
from typing import Callable, Optional

from .audio_device_manager import AudioDeviceManager

logger = logging.getLogger("MacAssistant.MicrophoneService")


class MicrophoneService:
    """Thread-safe microphone capture service.

    Features:
    - Pins to Built-in or USB mic, avoiding Bluetooth HFP low-quality drop.
    - Captures at native hardware sample rate (44.1k/48k) and resamples to 16kHz in memory.
    - Re-evaluates devices dynamically when devices connect or disconnect.
    - Anti-loop feedback protection while assistant speaks.
    """

    def __init__(
        self,
        rate: int = 16000,
        chunk_size: int = 1024,
        speech_threshold: float = 120.0,
        silence_duration: float = 1.0,
        microphone_mode: str = "builtin",
        preferred_device: Optional[str] = None
    ):
        self.target_rate = 16000
        self.native_rate = rate
        self.chunk_size = chunk_size
        self.speech_threshold = speech_threshold
        self.silence_duration = silence_duration
        self.microphone_mode = microphone_mode
        self.preferred_device = preferred_device

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stream = None
        self._pyaudio_instance = None
        self._is_speaking = False
        self._is_muted = False
        self._current_device_name = "None"
        self._is_bt_mic_active = False

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    def set_muted(self, muted: bool) -> None:
        self._is_muted = muted
        logger.info("Microphone muted state set to: %s", muted)

    def set_speaking_state(self, is_speaking: bool) -> None:
        """Mutes mic processing while the Mac is speaking to prevent feedback loops."""
        self._is_speaking = is_speaking

    def start_listening(
        self,
        on_speech_chunk: Callable[[bytes], None],
        device_index: Optional[int] = None
    ) -> bool:
        """Starts persistent audio capture thread pinned to the selected input device."""
        with self._lock:
            if self._running:
                logger.warning("MicrophoneService is already running.")
                return True

            if self.microphone_mode == "off":
                logger.info("Microphone capture disabled (mode='off').")
                return False

            try:
                import pyaudio
            except ImportError:
                logger.error("pyaudio is required for MicrophoneService.")
                return False

            self._pyaudio_instance = pyaudio.PyAudio()

            # Resolve device according to configured mode (builtin / default / preferred)
            resolved_idx, native_rate, dev_name, is_bt = AudioDeviceManager.resolve_mic_device(
                self._pyaudio_instance,
                mode=self.microphone_mode,
                preferred_name=self.preferred_device
            )

            if resolved_idx is None:
                logger.warning("No functional audio input device available.")
                self._pyaudio_instance.terminate()
                self._pyaudio_instance = None
                return False

            self.native_rate = native_rate
            self._current_device_name = dev_name
            self._is_bt_mic_active = is_bt

            if is_bt:
                logger.warning(
                    "⚠️  Bluetooth headset '%s' is acting as input. This may downgrade macOS audio output to 16kHz SCO/HFP.",
                    dev_name
                )

            # Native chunk size proportional to sample rate (preserving ~64ms window)
            native_chunk = int(self.chunk_size * (self.native_rate / 16000.0))

            try:
                # Open plain capture stream without voice processing IO units
                self._stream = self._pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.native_rate,
                    input=True,
                    input_device_index=resolved_idx,
                    frames_per_buffer=native_chunk
                )
            except Exception as e:
                logger.error("Failed opening microphone stream on [%d] '%s': %s", resolved_idx, dev_name, e)
                self._pyaudio_instance.terminate()
                self._pyaudio_instance = None
                return False

            self._running = True
            self._thread = threading.Thread(
                target=self._capture_loop,
                args=(on_speech_chunk, native_chunk),
                name="MacAssistant-MicWorker",
                daemon=True
            )
            self._thread.start()
            logger.info(
                "Microphone stream active on [%d] '%s' at native %d Hz (resampling to 16 kHz).",
                resolved_idx, dev_name, self.native_rate
            )
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

    def _capture_loop(self, on_speech_chunk: Callable[[bytes], None], native_chunk: int) -> None:
        """Worker loop reading frames, resampling to 16kHz, detecting speech and silence."""
        audio_buffer = []
        is_speech_active = False
        silence_start_time = None
        pre_roll_buffer = collections.deque(maxlen=4)

        while self._running:
            if self._is_muted or self._is_speaking:
                time.sleep(0.05)
                continue

            try:
                raw_data = self._stream.read(native_chunk, exception_on_overflow=False)
            except Exception as e:
                logger.debug("Mic read error: %s", e)
                time.sleep(0.05)
                continue

            # Resample native audio (44.1k/48k) to standard 16kHz
            resampled_16k = AudioDeviceManager.resample_to_16k(raw_data, self.native_rate)

            num_samples = len(resampled_16k) // 2
            if num_samples == 0:
                continue

            shorts = struct.unpack(f"{num_samples}h", resampled_16k)
            sum_squares = sum(s * s for s in shorts)
            rms = math.sqrt(sum_squares / num_samples)

            if rms >= self.speech_threshold:
                if not is_speech_active:
                    is_speech_active = True
                    audio_buffer = list(pre_roll_buffer)
                    logger.debug("Speech start detected (RMS: %.0f)", rms)
                audio_buffer.append(resampled_16k)
                silence_start_time = None
            else:
                if is_speech_active:
                    audio_buffer.append(resampled_16k)
                    now = time.time()
                    if silence_start_time is None:
                        silence_start_time = now
                    elif now - silence_start_time >= self.silence_duration:
                        complete_utterance = b"".join(audio_buffer)
                        audio_buffer.clear()
                        is_speech_active = False
                        silence_start_time = None
                        try:
                            on_speech_chunk(complete_utterance)
                        except Exception as cb_err:
                            logger.error("Error in on_speech_chunk callback: %s", cb_err)
                else:
                    pre_roll_buffer.append(resampled_16k)
