"""Built-in media control skill for Spotify and Apple Music."""

import logging
import subprocess
from typing import Any, Dict

from .registry import BaseSkill, SkillResult

logger = logging.getLogger("MacAssistant.Skills.Media")


class MediaSkill(BaseSkill):
    name = "media_control"
    description = "Controls media playback on Spotify or Apple Music"
    triggers = [
        "play music", "pause music", "stop music", "resume music",
        "next song", "next track", "skip song",
        "previous song", "previous track"
    ]

    def handle(self, utterance: str, persona: str, config: Dict[str, Any]) -> SkillResult:
        clean = utterance.strip().lower()

        if any(w in clean for w in ["pause", "stop"]):
            action = "pause"
        elif any(w in clean for w in ["next", "skip"]):
            action = "next track"
        elif "previous" in clean:
            action = "previous track"
        else:
            action = "play"

        script = f'''
        tell application "Spotify"
            if running then
                {action}
                return "Spotify"
            end if
        end tell
        tell application "Music"
            if running then
                {action}
                return "Music"
            end if
        end tell
        return "None"
        '''
        try:
            res = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=2.0)
            target_app = res.stdout.strip()
            if target_app != "None":
                reply = "Right away, Sir." if persona.lower() == "jarvis" else "On it!"
                return SkillResult(handled=True, response=reply, action_taken=action)
            else:
                reply = "No active media players were found running, Sir." if persona.lower() == "jarvis" else "Neither Spotify nor Apple Music is currently open."
                return SkillResult(handled=True, response=reply)
        except Exception as e:
            logger.error("Media control error: %s", e)
            return SkillResult(handled=True, response="Could not adjust media playback.")
