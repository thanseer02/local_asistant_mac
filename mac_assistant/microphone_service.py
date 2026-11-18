"""Single shared microphone capture service with device hard-pinning, listen_mode, and stream release.

Supports listen_mode:
- "always": Captures continuously on non-Bluetooth built-in mic.
- "push_to_talk": Stream is completely closed; opens on trigger and closes after command/silence.
- "smart": Closes stream completely when media is playing on Bluetooth, screen is locked,
  during quiet hours, or on 'stop listening', turning the orange mic indicator OFF.
"""

import collections
import logging
import math
import struct
import threading
import time
from typing import Callable, Optional

from .audio_device_manager import AudioDeviceManager
from .audio_diagnostics import AudioDiagnostics

logger = logging.getLogger("MacAssistant.MicrophoneService")


class MicrophoneService:
    """Thread-safe, single shared microphone capture stream.

    Guarantees:
    - Never opens multiple audio streams.
    - Never opens a Bluetooth input in 'builtin' mode.
    - Closes stream completely when inactive so the macOS orange mic dot turns off.
    - Resamples native 44.1k/48k audio to 16kHz in memory.
    """

    _active_stream_count: int = 0
    _count_lock = threading.Lock()

    def __init__(
        self,
        rate: int = 16000,
        chunk_size: int = 1024,
        speech_threshold: float = 120.0,
        silence_duration: float = 1.0,
        microphone_mode: str = "builtin",
        pinned_device: Optional[str] = None,
        listen_mode: str = "smart"
    ):
        self.target_rate = 16000
        self.native_rate = rate
        self.chunk_size = chunk_size
        self.speech_threshold = speech_threshold
        self.silence_duration = silence_duration
        self.microphone_mode = microphone_mode
        self.pinned_device = pinned_device
        self.listen_mode = listen_mode  # "always", "push_to_talk", "smart"

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stream = None
        self._pyaudio_instance = None
        self._is_speaking = False
        self._is_muted = False
        self._current_device_name = "None"
        self._current_device_index: Optional[int] = None
        self._last_speech_callback: Optional[Callable[[bytes], None]] = None

    @classmethod
    def get_active_stream_count(cls) -> int:
        with cls._count_lock:
            return cls._active_stream_count

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    @property
    def is_stream_open(self) -> bool:
        return self._stream is not None

    @property
    def active_device_name(self) -> str:
        return self._current_device_name

    def set_muted(self, muted: bool) -> None:
        self._is_muted = muted
        logger.info("Microphone muted state set to: %s", muted)
        if muted and self._stream:
            self.stop_listening()

    def set_speaking_state(self, is_speaking: bool) -> None:
        self._is_speaking = is_speaking

    def start_listening(
        self,
        on_speech_chunk: Callable[[bytes], None],
        device_index: Optional[int] = None
    ) -> bool:
        """Opens the single shared capture stream on the pinned non-Bluetooth device."""
        with self._lock:
            if self._running:
                logger.debug("MicrophoneService already has an active capture stream.")
                return True

            if self.microphone_mode == "off" or self._is_muted:
                logger.info("Microphone listening is currently off/muted.")
                return False

            self._last_speech_callback = on_speech_chunk

            # Smart mode check: if media is playing via Bluetooth, keep stream closed!
            if self.listen_mode == "smart":
                hfp_active, _ = AudioDiagnostics.is_bluetooth_hfp_active()
                if hfp_active or AudioDeviceManager.is_media_playing():
                    logger.info("Smart mode: Media is active. Keeping mic stream closed to preserve high-quality A2DP.")
                    return False

            try:
                import pyaudio
            except ImportError:
                logger.error("pyaudio is required for MicrophoneService.")
                return False

            self._pyaudio_instance = pyaudio.PyAudio()

            # Strictly resolve input by name, refusing Bluetooth in builtin mode
            res_idx, native_rate, dev_name, status = AudioDeviceManager.resolve_mic_device(
                self._pyaudio_instance,
                microphone_mode=self.microphone_mode,
                pinned_device_name=self.pinned_device
            )

            if res_idx is None:
                logger.warning("Microphone stream NOT opened: %s", status)
                self._pyaudio_instance.terminate()
                self._pyaudio_instance = None
                self._current_device_name = "None"
                return False

            self.native_rate = native_rate
            self._current_device_index = res_idx
            self._current_device_name = dev_name

            native_chunk = int(self.chunk_size * (self.native_rate / 16000.0))

            try:
                # Plain capture stream without echo cancellation or voice processing IO units
                self._stream = self._pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.native_rate,
                    input=True,
                    input_device_index=res_idx,
                    frames_per_buffer=native_chunk
                )
                with MicrophoneService._count_lock:
                    MicrophoneService._active_stream_count += 1
            except Exception as e:
                logger.error("Failed opening microphone stream on [%d] '%s': %s", res_idx, dev_name, e)
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
                "Capture stream OPENED on [%d] '%s' at native %d Hz (single shared stream active).",
                res_idx, dev_name, self.native_rate
            )
            return True

    def stop_listening(self) -> None:
        """Completely closes the audio stream so the macOS orange mic dot turns off."""
        with self._lock:
            if not self._running and self._stream is None:
                return
            self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                    with MicrophoneService._count_lock:
                        MicrophoneService._active_stream_count = max(0, MicrophoneService._active_stream_count - 1)
                except Exception:
                    pass
                self._stream = None

            if self._pyaudio_instance:
                try:
                    self._pyaudio_instance.terminate()
                except Exception:
                    pass
                self._pyaudio_instance = None

        logger.info("Capture stream CLOSED completely. Orange mic dot turned OFF.")

    def trigger_push_to_talk(self, duration: float = 6.0) -> None:
        """Opens capture for push-to-talk, automatically closing after silence or timeout."""
        if self._last_speech_callback:
            self.start_listening(self._last_speech_callback)

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

                        # If in push_to_talk mode, close stream immediately after utterance
                        if self.listen_mode == "push_to_talk":
                            logger.info("Push-to-talk utterance completed. Auto-closing stream.")
                            threading.Thread(target=self.stop_listening, daemon=True).start()
                            break
                else:
                    pre_roll_buffer.append(resampled_16k)
