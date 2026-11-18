"""Stage 2: Voice Activity Detection (VAD).

Detects speech start and speech end, computing trailing silence
to signal utterance completion and close the capture state between commands.
"""

import logging
import math
import struct
import time
from typing import Optional

from .interfaces import AudioFrame, VoiceActivityDetector

logger = logging.getLogger("MacAssistant.Pipeline.VAD")


class EnergyVADStage(VoiceActivityDetector):
    """Energy & spectral Voice Activity Detector."""

    def __init__(self, speech_threshold: float = 120.0, silence_timeout: float = 1.0):
        self.speech_threshold = speech_threshold
        self.silence_timeout = silence_timeout
        self.speech_active = False
        self.silence_start_time: Optional[float] = None

    def is_speech(self, frame: AudioFrame) -> bool:
        if not frame.data:
            return False

        num_samples = len(frame.data) // 2
        if num_samples == 0:
            return False

        shorts = struct.unpack(f"{num_samples}h", frame.data)
        sum_squares = sum(s * s for s in shorts)
        rms = math.sqrt(sum_squares / num_samples)

        is_active = rms >= self.speech_threshold
        now = time.time()

        if is_active:
            self.speech_active = True
            self.silence_start_time = None
            return True
        else:
            if self.speech_active:
                if self.silence_start_time is None:
                    self.silence_start_time = now
                elif now - self.silence_start_time >= self.silence_timeout:
                    self.speech_active = False
                    self.silence_start_time = None
                    return False
                return True
            return False

    def reset(self) -> None:
        self.speech_active = False
        self.silence_start_time = None
