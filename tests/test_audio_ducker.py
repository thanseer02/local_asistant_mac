"""Unit tests for AudioDucker and ducking behavior."""

import unittest
from unittest.mock import MagicMock, patch

from mac_assistant.audio_ducker import AudioDucker, DuckSession, DuckTarget


class TestAudioDucker(unittest.TestCase):

    def setUp(self):
        self.ducker = AudioDucker()
        self.config = {
            "audio_ducking": {
                "enabled": True,
                "duck_level": 0.25,
                "duck_system_volume": True
            }
        }

    @patch.object(AudioDucker, "_get_music_volume_if_playing", return_value=80)
    @patch.object(AudioDucker, "_set_music_volume", return_value=True)
    def test_duck_music_app_when_playing(self, mock_set_vol, mock_get_vol):
        session = self.ducker.duck(self.config)
        self.assertIsNotNone(session)
        self.assertEqual(session.target, DuckTarget.MUSIC_APP)
        self.assertEqual(session.original_volume, 80)
        self.assertEqual(session.ducked_volume, 20)  # 80 * 0.25
        mock_set_vol.assert_called_once_with(20)

        # Unduck restores original volume
        self.ducker.unduck(session)
        mock_set_vol.assert_called_with(80)

    @patch.object(AudioDucker, "_get_music_volume_if_playing", return_value=None)
    @patch.object(AudioDucker, "_get_spotify_volume_if_playing", return_value=100)
    @patch.object(AudioDucker, "_set_spotify_volume", return_value=True)
    def test_duck_spotify_when_playing(self, mock_set_vol, mock_get_vol, mock_music):
        session = self.ducker.duck(self.config)
        self.assertIsNotNone(session)
        self.assertEqual(session.target, DuckTarget.SPOTIFY)
        self.assertEqual(session.original_volume, 100)
        self.assertEqual(session.ducked_volume, 25)  # 100 * 0.25
        mock_set_vol.assert_called_once_with(25)

        self.ducker.unduck(session)
        mock_set_vol.assert_called_with(100)

    @patch.object(AudioDucker, "_get_music_volume_if_playing", return_value=None)
    @patch.object(AudioDucker, "_get_spotify_volume_if_playing", return_value=None)
    @patch.object(AudioDucker, "_get_system_volume", return_value=60)
    @patch.object(AudioDucker, "_set_system_volume", return_value=True)
    def test_duck_system_volume_fallback(self, mock_set_sys, mock_get_sys, mock_spot, mock_music):
        session = self.ducker.duck(self.config)
        self.assertIsNotNone(session)
        self.assertEqual(session.target, DuckTarget.SYSTEM)
        self.assertEqual(session.original_volume, 60)
        self.assertEqual(session.ducked_volume, 15)  # 60 * 0.25
        mock_set_sys.assert_called_once_with(15)

        self.ducker.unduck(session)
        mock_set_sys.assert_called_with(60)

    @patch.object(AudioDucker, "_get_music_volume_if_playing", return_value=80)
    @patch.object(AudioDucker, "_set_music_volume", return_value=True)
    def test_reentrant_nested_ducking(self, mock_set_vol, mock_get_vol):
        # 1st speech request
        s1 = self.ducker.duck(self.config)
        self.assertEqual(s1.original_volume, 80)
        self.assertEqual(mock_set_vol.call_count, 1)

        # 2nd overlapping speech request
        s2 = self.ducker.duck(self.config)
        self.assertEqual(s1, s2)
        # Should not set volume a second time
        self.assertEqual(mock_set_vol.call_count, 1)

        # 1st speech ends - volume should NOT be restored yet
        self.ducker.unduck(s1)
        self.assertEqual(mock_set_vol.call_count, 1)

        # 2nd speech ends - volume restored to original 80
        self.ducker.unduck(s2)
        self.assertEqual(mock_set_vol.call_count, 2)
        mock_set_vol.assert_called_with(80)

    def test_disabled_ducking(self):
        cfg = {"audio_ducking": {"enabled": False}}
        session = self.ducker.duck(cfg)
        self.assertIsNone(session)


if __name__ == "__main__":
    unittest.main()
