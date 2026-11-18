"""Kokoro ONNX lazy-loaded singleton engine with CoreML/CPU acceleration and audio caching."""

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("MacAssistant.KokoroEngine")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "kokoro" / "kokoro-v1.0.onnx"
DEFAULT_VOICES_PATH = PROJECT_ROOT / "models" / "kokoro" / "voices-v1.0.bin"
AUDIO_CACHE_DIR = PROJECT_ROOT / "data" / "audio_cache"


class KokoroEngine:
    """
    Thread-safe lazy-loaded singleton for Kokoro TTS.
    - Zero idle CPU: Model is not initialized until first synthesis request.
    - Uses CoreML on Apple Silicon where available, falling back smoothly to multi-threaded CPU.
    - Disk-cached audio files for repeating phrases (greetings, reminders, goodbyes).
    """

    _instance: Optional["KokoroEngine"] = None
    _init_lock = threading.Lock()

    def __init__(self, model_path: Optional[Path] = None, voices_path: Optional[Path] = None):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.voices_path = voices_path or DEFAULT_VOICES_PATH
        self.cache_dir = AUDIO_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._kokoro = None
        self._load_lock = threading.Lock()
        self._load_failed = False
        self._failure_reason = ""

    @classmethod
    def get_instance(cls) -> "KokoroEngine":
        """Returns the process-wide KokoroEngine singleton."""
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = KokoroEngine()
            return cls._instance

    def is_model_available(self) -> bool:
        """Checks if ONNX model and voices file exist on disk."""
        return self.model_path.exists() and self.voices_path.exists()

    def _ensure_loaded(self) -> bool:
        """Lazy-loads Kokoro ONNX model on first speech call."""
        if self._kokoro is not None:
            return True
        if self._load_failed:
            return False

        with self._load_lock:
            if self._kokoro is not None:
                return True
            if not self.is_model_available():
                self._load_failed = True
                self._failure_reason = f"Kokoro model files not found: {self.model_path} or {self.voices_path}"
                logger.warning(self._failure_reason)
                return False

            try:
                logger.info("Lazy-loading Kokoro ONNX engine from %s...", self.model_path)
                t0 = time.time()
                import onnxruntime as ort
                from kokoro_onnx import Kokoro

                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = 4
                sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                # Prefer CoreML for hardware acceleration on Apple Silicon, fallback to CPU
                available = ort.get_available_providers()
                providers = []
                if "CoreMLExecutionProvider" in available:
                    providers.append("CoreMLExecutionProvider")
                providers.append("CPUExecutionProvider")

                session = ort.InferenceSession(
                    str(self.model_path.resolve()),
                    sess_options=sess_options,
                    providers=providers
                )

                kokoro_inst = Kokoro(
                    str(self.model_path.resolve()),
                    str(self.voices_path.resolve())
                )
                kokoro_inst.sess = session

                self._kokoro = kokoro_inst
                logger.info("Kokoro ONNX engine initialized in %.2fs (providers=%s)", time.time() - t0, providers)
                return True
            except Exception as e:
                self._load_failed = True
                self._failure_reason = str(e)
                logger.error("Failed to initialize Kokoro ONNX engine: %s", e)
                return False

    def _get_cache_path(self, text: str, voice: str, speed: float, lang: str) -> Path:
        """Computes deterministic cache filepath using sha256 hash."""
        key = f"{text.strip().lower()}|{voice}|{speed:.2f}|{lang}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"kokoro_{h}.wav"

    def synthesize_to_wav(
        self,
        text: str,
        voice: str = "bm_george",
        speed: float = 1.0,
        lang: str = "en-us"
    ) -> Optional[Path]:
        """
        Synthesizes spoken text into a .wav file.
        Returns path to .wav file, or None if Kokoro failed.
        """
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        cached_file = self._get_cache_path(clean_text, voice, speed, lang)
        if cached_file.exists() and cached_file.stat().st_size > 44:
            return cached_file

        if not self._ensure_loaded():
            return None

        try:
            import soundfile as sf
            t0 = time.time()
            samples, sample_rate = self._kokoro.create(
                clean_text,
                voice=voice,
                speed=speed,
                lang=lang
            )
            # Write atomically to cache
            tmp_path = cached_file.with_name(f"{cached_file.stem}_tmp.wav")
            sf.write(str(tmp_path), samples, sample_rate, format="WAV")
            os.replace(tmp_path, cached_file)
            logger.debug("Synthesized sentence in %.2fs: '%s'", time.time() - t0, clean_text[:40])
            return cached_file
        except Exception as e:
            logger.error("Kokoro synthesis error for '%s': %s", clean_text[:40], e)
            return None
