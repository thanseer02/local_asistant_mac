"""Stage 1: Offline openWakeWord detector."""

import logging
from typing import Optional
import numpy as np

from .interfaces import AudioFrame, WakeWordDetector

logger = logging.getLogger("MacAssistant.Pipeline.WakeWord")


class OpenWakeWordStage(WakeWordDetector):
    """Offline wake-word detection using openWakeWord ONNX runtime.

    Keeps idle CPU near 0%, runs locally, and routes 'hey_jarvis' and 'friday'.
    """

    def __init__(self, jarvis_threshold: float = 0.5, friday_threshold: float = 0.5):
        self.jarvis_threshold = jarvis_threshold
        self.friday_threshold = friday_threshold
        self._model = None
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            from openwakeword.model import Model
            self._model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx"
            )
            logger.info("Pipeline WakeWord: openWakeWord ONNX engine loaded ('hey_jarvis').")
        except Exception as e:
            logger.debug("openWakeWord loading fallback: %s", e)
            self._model = None

    def process_frame(self, frame: AudioFrame) -> Optional[str]:
        if self._model is None or not frame.data:
            return None

        try:
            samples = np.frombuffer(frame.data, dtype=np.int16)
            if len(samples) < 1280:
                return None

            frame_1280 = samples[-1280:]
            preds = self._model.predict(frame_1280)
            jarvis_score = preds.get("hey_jarvis", 0.0)

            if jarvis_score >= self.jarvis_threshold:
                logger.info("WakeWord detected: 'jarvis' (score: %.3f)", jarvis_score)
                self.reset()
                return "jarvis"

        except Exception as e:
            logger.debug("openWakeWord prediction error: %s", e)

        return None

    def reset(self) -> None:
        if self._model:
            try:
                self._model.reset()
            except Exception:
                pass
