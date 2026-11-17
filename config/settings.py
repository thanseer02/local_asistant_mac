"""Centralized typed configuration settings with .env support."""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env if present
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class AudioSettings(BaseModel):
    sample_rate: int = 24000  # OpenAI Realtime standard
    channels: int = 1
    chunk_size: int = 1024
    mic_index: Optional[int] = 0  # 0 is WH-CH510 / primary input
    speaker_index: Optional[int] = None
    speech_threshold: float = 120.0  # RMS speech onset
    silence_duration: float = 0.8  # Trailing silence


class RealtimeSettings(BaseModel):
    api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = "gpt-4o-realtime-preview-2024-12-17"
    voice: str = "alloy"  # alloy, ash, ballad, coral, echo, sage, shimmer, verse
    modalities: List[str] = ["audio", "text"]
    turn_detection_mode: str = "server_vad"  # server_vad handles automatic turn cut & barge-in
    temperature: float = 0.7
    max_response_output_tokens: int = 800


class AppSettings(BaseModel):
    user_name: str = "Sir"
    assistant_name: str = "Jarvis"
    persona: str = "jarvis"  # jarvis / friday
    audio: AudioSettings = Field(default_factory=AudioSettings)
    realtime: RealtimeSettings = Field(default_factory=RealtimeSettings)
    debug: bool = False


# Global singleton settings
settings = AppSettings()


def get_settings() -> AppSettings:
    """Reloads and returns settings."""
    global settings
    load_dotenv(ROOT_DIR / ".env", override=True)
    settings = AppSettings()
    return settings
