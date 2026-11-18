"""Fuzzy matching and command resolution for app names and user intent."""

import difflib
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("MacAssistant.FuzzyMatcher")

KNOWN_APPS = [
    "Google Chrome",
    "Visual Studio Code",
    "Terminal",
    "Brave Browser",
    "Spotify",
    "Slack",
    "Antigravity",
    "Discord",
    "Sublime Text",
    "Xcode",
    "Finder",
    "System Settings",
    "Calendar",
    "Notes",
    "Reminders",
    "Messages"
]

APP_ALIASES = {
    "chrome": "Google Chrome",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "brave": "Brave Browser",
    "term": "Terminal",
    "iterm": "Terminal",
    "antigravity": "Antigravity",
    "notes": "Notes",
    "apple notes": "Notes",
    "calendar": "Calendar",
    "settings": "System Settings"
}


class FuzzyCommandMatcher:
    """Matches spoken app names and commands against known allowlists using fuzzy similarity."""

    @classmethod
    def resolve_app_name(cls, query: str, threshold: float = 0.6) -> Tuple[Optional[str], float]:
        """Resolves fuzzy or alias app name. Returns (resolved_app_name, confidence)."""
        clean = query.strip().lower()

        # Direct alias check
        if clean in APP_ALIASES:
            return APP_ALIASES[clean], 1.0

        # Substring exact check
        for app in KNOWN_APPS:
            if clean in app.lower() or app.lower() in clean:
                return app, 0.95

        # Difflib similarity
        matches = difflib.get_close_matches(clean, [a.lower() for a in KNOWN_APPS], n=1, cutoff=threshold)
        if matches:
            matched_lower = matches[0]
            real_name = next(a for a in KNOWN_APPS if a.lower() == matched_lower)
            ratio = difflib.SequenceMatcher(None, clean, matched_lower).ratio()
            return real_name, ratio

        return None, 0.0
