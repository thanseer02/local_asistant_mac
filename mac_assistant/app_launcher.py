"""App launcher for morning/first login of the day."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("MacAssistant.AppLauncher")


class AppLauncher:
    """Launches user applications on session start / first login."""

    @staticmethod
    def launch_workspace(config: Dict[str, Any]) -> None:
        """Opens Antigravity, Google Chrome, Brave, Spotify, and Teams web/desktop."""
        apps_cfg = config.get("startup_apps", {})
        if not apps_cfg.get("enabled", True):
            return

        logger.info("Initializing startup workspace applications...")

        # 1. Antigravity IDE
        if apps_cfg.get("open_antigravity", True):
            subprocess.Popen(["/usr/bin/open", "-a", "Antigravity IDE"])

        # 2. Google Chrome (Teams and any specific profile/tabs)
        if apps_cfg.get("open_chrome", True):
            chrome_args = ["/usr/bin/open", "-a", "Google Chrome"]
            profile_dir = apps_cfg.get("chrome_profile_directory")
            
            # Target URLs: Microsoft Teams in Chrome
            teams_url = apps_cfg.get("teams_url", "https://teams.microsoft.com")
            
            if profile_dir:
                subprocess.Popen(["/usr/bin/open", "-a", "Google Chrome", "--args", f"--profile-directory={profile_dir}", teams_url])
            else:
                subprocess.Popen(["/usr/bin/open", "-a", "Google Chrome", teams_url])

        # 3. Brave Browser with Spotify and YouTube Music
        if apps_cfg.get("open_brave", True):
            brave_urls = apps_cfg.get("brave_urls", [
                "https://open.spotify.com",
                "https://music.youtube.com"
            ])
            subprocess.Popen(["/usr/bin/open", "-a", "Brave Browser", *brave_urls])
