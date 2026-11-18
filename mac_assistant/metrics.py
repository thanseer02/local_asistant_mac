"""Performance and telemetry metrics tracker for MacAssistant (--stats)."""

from collections import deque
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List

logger = logging.getLogger("MacAssistant.Metrics")

METRICS_FILE = Path(__file__).resolve().parent.parent / "data" / "metrics.json"


class MetricsTracker:
    """Tracks latency (STT, LLM, TTS), wake-word triggers, and system stats."""

    _stt_latencies: deque = deque(maxlen=50)
    _llm_latencies: deque = deque(maxlen=50)
    _wake_triggers: int = 0
    _commands_executed: int = 0

    @classmethod
    def record_wake_trigger(cls) -> None:
        cls._wake_triggers += 1

    @classmethod
    def record_command(cls) -> None:
        cls._commands_executed += 1

    @classmethod
    def record_stt_latency(cls, duration_seconds: float) -> None:
        cls._stt_latencies.append(duration_seconds)

    @classmethod
    def record_llm_latency(cls, duration_seconds: float) -> None:
        cls._llm_latencies.append(duration_seconds)

    @classmethod
    def get_stats_summary(cls) -> Dict[str, Any]:
        avg_stt = sum(cls._stt_latencies) / len(cls._stt_latencies) if cls._stt_latencies else 0.0
        avg_llm = sum(cls._llm_latencies) / len(cls._llm_latencies) if cls._llm_latencies else 0.0

        return {
            "wake_triggers": cls._wake_triggers,
            "commands_executed": cls._commands_executed,
            "avg_stt_latency_ms": round(avg_stt * 1000, 1),
            "avg_llm_latency_ms": round(avg_llm * 1000, 1),
        }

    @classmethod
    def print_report(cls) -> None:
        stats = cls.get_stats_summary()
        print("\n📊 MacAssistant Performance Metrics (--stats)\n" + "=" * 50)
        print(f"• Total Wake Triggers:       {stats['wake_triggers']}")
        print(f"• Total Commands Executed:   {stats['commands_executed']}")
        print(f"• Average STT Latency:       {stats['avg_stt_latency_ms']} ms")
        print(f"• Average LLM Latency:       {stats['avg_llm_latency_ms']} ms")
        print("=" * 50 + "\n")
