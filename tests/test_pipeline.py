"""Unit tests verifying the modular on-device voice pipeline stages."""

import unittest
from mac_assistant.pipeline.action import PluginActionStage
from mac_assistant.pipeline.coordinator import VoicePipelineCoordinator
from mac_assistant.pipeline.interfaces import AudioFrame
from mac_assistant.pipeline.stt import UnifiedSTTStage
from mac_assistant.pipeline.vad import EnergyVADStage
from mac_assistant.pipeline.wake_word import OpenWakeWordStage


class TestPipelineArchitecture(unittest.TestCase):

    def setUp(self):
        self.config = {
            "assistant_persona": "friday",
            "stt_provider": "apple",
            "voice_commands": {"speech_threshold": 120.0, "silence_duration": 1.0}
        }
        self.coordinator = VoicePipelineCoordinator(self.config)

    def test_wake_word_stage_offline_initialization(self):
        detector = OpenWakeWordStage()
        self.assertIsNotNone(detector)
        detector.reset()

    def test_vad_stage_energy_detection(self):
        vad = EnergyVADStage(speech_threshold=100.0, silence_timeout=0.5)
        silent_frame = AudioFrame(data=b"\x00" * 2048, sample_rate=16000)
        self.assertFalse(vad.is_speech(silent_frame))

    def test_stt_unified_stage_creation(self):
        stt = UnifiedSTTStage(preferred_provider="apple")
        self.assertIsNotNone(stt.apple)
        self.assertIsNotNone(stt.whisper)

    def test_action_stage_registry(self):
        actions = PluginActionStage()
        actions.register_action("test_action", lambda **kwargs: (True, "Action Success"))
        ok, res = actions.execute("test_action")
        self.assertTrue(ok)
        self.assertEqual(res, "Action Success")

    def test_coordinator_routing(self):
        intent, ok, reply = self.coordinator.execute_speech_pipeline(b"", persona="friday")
        self.assertEqual(intent, "empty")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
