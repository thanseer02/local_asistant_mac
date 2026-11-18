"""Audio ducking manager for MacAssistant.

Automatically detects active music playback (Music.app, Spotify, or background audio)
and ducks the volume when the assistant speaks, restoring it smoothly afterwards.
"""

from dataclasses import dataclass
import enum
import logging
import subprocess
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("MacAssistant.AudioDucker")


class DuckTarget(enum.Enum):
    NONE = "none"
    MUSIC_APP = "music_app"
    SPOTIFY = "spotify"
    SYSTEM = "system"


@dataclass
class DuckSession:
    target: DuckTarget
    original_volume: int
    ducked_volume: int


class AudioDucker:
    """
    Manages audio ducking across macOS media apps and system audio.
    - If Apple Music is playing, ducks Apple Music's application sound volume.
    - If Spotify desktop is playing, ducks Spotify's application sound volume.
    - If enabled and system ducking mode is selected, ducks macOS master output volume.
    - Thread-safe with support for nested/re-entrant calls (retains original volume).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active_session: Optional[DuckSession] = None
        self._nesting_depth: int = 0

    def duck(self, config: Dict[str, Any]) -> Optional[DuckSession]:
        """
        Ducks volume if ducking is enabled in config.
        Returns the active DuckSession, or None if ducking was not performed.
        """
        duck_cfg = config.get("audio_ducking", {})
        if not duck_cfg.get("enabled", True):
            return None

        duck_level = float(duck_cfg.get("duck_level", 0.25))  # 25% of current volume
        allow_system_duck = bool(duck_cfg.get("duck_system_volume", True))

        with self._lock:
            # If already ducked, increase nesting depth and keep initial original volume
            if self._active_session is not None:
                self._nesting_depth += 1
                return self._active_session

            session = self._perform_duck(duck_level=duck_level, allow_system_duck=allow_system_duck)
            if session:
                self._active_session = session
                self._nesting_depth = 1
            return session

    def unduck(self, session: Optional[DuckSession] = None) -> None:
        """
        Restores volume to its original level before ducking occurred.
        Safe to call even if not ducked or session is None.
        """
        with self._lock:
            if self._active_session is None:
                return

            self._nesting_depth -= 1
            if self._nesting_depth > 0:
                return

            sess = self._active_session
            self._active_session = None
            self._nesting_depth = 0

            self._perform_unduck(sess)

    def _perform_duck(self, duck_level: float, allow_system_duck: bool) -> Optional[DuckSession]:
        # 1. Check if Apple Music is playing
        music_vol = self._get_music_volume_if_playing()
        if music_vol is not None:
            ducked = max(5, int(music_vol * duck_level))
            if self._set_music_volume(ducked):
                logger.info("Ducked Music.app volume: %d -> %d", music_vol, ducked)
                return DuckSession(target=DuckTarget.MUSIC_APP, original_volume=music_vol, ducked_volume=ducked)

        # 2. Check if Spotify desktop is playing
        spotify_vol = self._get_spotify_volume_if_playing()
        if spotify_vol is not None:
            ducked = max(5, int(spotify_vol * duck_level))
            if self._set_spotify_volume(ducked):
                logger.info("Ducked Spotify volume: %d -> %d", spotify_vol, ducked)
                return DuckSession(target=DuckTarget.SPOTIFY, original_volume=spotify_vol, ducked_volume=ducked)

        # 3. System-level ducking (for YouTube Music, Spotify Web in Brave/Chrome, or general audio)
        if allow_system_duck:
            sys_vol = self._get_system_volume()
            if sys_vol is not None and sys_vol > 15:
                ducked = max(10, int(sys_vol * duck_level))
                if self._set_system_volume(ducked):
                    logger.info("Ducked macOS system volume: %d -> %d", sys_vol, ducked)
                    return DuckSession(target=DuckTarget.SYSTEM, original_volume=sys_vol, ducked_volume=ducked)

        return None

    def _perform_unduck(self, session: DuckSession) -> None:
        try:
            if session.target == DuckTarget.MUSIC_APP:
                self._set_music_volume(session.original_volume)
                logger.info("Restored Music.app volume to %d", session.original_volume)
            elif session.target == DuckTarget.SPOTIFY:
                self._set_spotify_volume(session.original_volume)
                logger.info("Restored Spotify volume to %d", session.original_volume)
            elif session.target == DuckTarget.SYSTEM:
                self._set_system_volume(session.original_volume)
                logger.info("Restored macOS system volume to %d", session.original_volume)
        except Exception as e:
            logger.error("Error during volume unducking: %s", e)

    # --- Helper methods ---

    def _is_process_running(self, process_name: str) -> bool:
        try:
            res = subprocess.run(["pgrep", "-x", process_name], capture_output=True, timeout=1.0)
            return res.returncode == 0
        except Exception:
            return False

    def _get_music_volume_if_playing(self) -> Optional[int]:
        if not self._is_process_running("Music"):
            return None
        try:
            state = subprocess.check_output(
                ["osascript", "-e", 'tell application "Music" to get (player state as string)'],
                text=True, stderr=subprocess.DEVNULL, timeout=1.5
            ).strip().lower()
            if state == "playing":
                vol_str = subprocess.check_output(
                    ["osascript", "-e", 'tell application "Music" to get sound volume'],
                    text=True, stderr=subprocess.DEVNULL, timeout=1.5
                ).strip()
                return int(float(vol_str))
        except Exception as e:
            logger.debug("Music.app status check error: %s", e)
        return None

    def _set_music_volume(self, volume: int) -> bool:
        try:
            subprocess.check_call(
                ["osascript", "-e", f'tell application "Music" to set sound volume to {volume}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.5
            )
            return True
        except Exception as e:
            logger.error("Failed to set Music.app volume: %s", e)
            return False

    def _get_spotify_volume_if_playing(self) -> Optional[int]:
        if not self._is_process_running("Spotify"):
            return None
        try:
            state = subprocess.check_output(
                ["osascript", "-e", 'tell application "Spotify" to get (player state as string)'],
                text=True, stderr=subprocess.DEVNULL, timeout=1.5
            ).strip().lower()
            if state == "playing":
                vol_str = subprocess.check_output(
                    ["osascript", "-e", 'tell application "Spotify" to get sound volume'],
                    text=True, stderr=subprocess.DEVNULL, timeout=1.5
                ).strip()
                return int(float(vol_str))
        except Exception as e:
            logger.debug("Spotify status check error: %s", e)
        return None

    def _set_spotify_volume(self, volume: int) -> bool:
        try:
            subprocess.check_call(
                ["osascript", "-e", f'tell application "Spotify" to set sound volume to {volume}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.5
            )
            return True
        except Exception as e:
            logger.error("Failed to set Spotify volume: %s", e)
            return False

    def _get_system_volume(self) -> Optional[int]:
        try:
            out = subprocess.check_output(
                ["osascript", "-e", "output volume of (get volume settings)"],
                text=True, stderr=subprocess.DEVNULL, timeout=1.5
            ).strip()
            return int(out)
        except Exception as e:
            logger.debug("Failed to get macOS system volume: %s", e)
            return None

    def _set_system_volume(self, volume: int) -> bool:
        try:
            subprocess.check_call(
                ["osascript", "-e", f"set volume output volume {volume}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.5
            )
            return True
        except Exception as e:
            logger.error("Failed to set macOS system volume: %s", e)
            return False
