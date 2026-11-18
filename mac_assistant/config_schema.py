"""Pydantic schema validation for MacAssistant config.json."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PersonaSettings(BaseModel):
    voice: str = "Moira"
    speech_rate: int = 172
    greetings: Optional[Dict[str, Any]] = None
    goodbyes: Optional[List[str]] = None


class HudSoundConfig(BaseModel):
    enabled: bool = True
    sound_file: str = "hud_chime.wav"


class VoiceCommandsConfig(BaseModel):
    enabled: bool = False
    wake_words: List[str] = Field(default_factory=lambda: ["hey jarvis", "hey friday", "jarvis", "friday"])
    mic_index: Optional[int] = None
    speech_threshold: float = 120.0
    silence_duration: float = 1.0
    command_timeout: float = 6.0
    wake_sensitivity: float = 0.5


class EyeBreakConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = 20
    friday_messages: Optional[List[str]] = None
    jarvis_messages: Optional[List[str]] = None


class HydrationConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = 30
    start_hour: int = 9
    end_hour: int = 21
    friday_messages: Optional[List[str]] = None
    jarvis_messages: Optional[List[str]] = None


class ScheduledReminderItem(BaseModel):
    time: str
    label: Optional[str] = None
    message: Optional[str] = None
    friday_message: Optional[str] = None
    jarvis_message: Optional[str] = None


class AppConfigSchema(BaseModel):
    assistant_persona: str = "friday"
    voice: str = "Moira"
    speech_rate: int = 172
    user_name: str = "Sir"
    login_delay_seconds: float = 0.5
    cooldown_seconds: float = 2.0
    hud_sound: HudSoundConfig = Field(default_factory=HudSoundConfig)
    voice_commands: VoiceCommandsConfig = Field(default_factory=VoiceCommandsConfig)
    eye_break_reminders: Optional[EyeBreakConfig] = None
    hydration_reminders: Optional[HydrationConfig] = None
    scheduled_reminders: Optional[List[ScheduledReminderItem]] = None
    personas: Optional[Dict[str, PersonaSettings]] = None

    class Config:
        extra = "allow"
