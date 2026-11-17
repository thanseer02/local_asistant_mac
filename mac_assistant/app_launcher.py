"""App launcher for morning/first login of the day with duplicate tab prevention."""

import logging
import subprocess
from typing import Any, Dict, List

logger = logging.getLogger("MacAssistant.AppLauncher")


class AppLauncher:
    """Launches user applications on session start / first login with tab duplicate checks."""

    @staticmethod
    def _get_open_urls(browser_name: str) -> List[str]:
        """
        Queries Chromium-based browsers (Google Chrome, Brave Browser) for currently open tab URLs.
        Returns an empty list if browser is closed or has no tabs open.
        """
        applescript = f'''
        tell application "{browser_name}"
            try
                if not running then
                    return ""
                end if
                set urlStr to ""
                repeat with w in windows
                    repeat with t in tabs of w
                        set urlStr to urlStr & (URL of t) & "\\n"
                    end repeat
                end repeat
                return urlStr
            on error
                return ""
            end try
        end tell
        '''
        try:
            res = subprocess.run(
                ["/usr/bin/osascript", "-e", applescript],
                capture_output=True,
                text=True,
                timeout=5
            )
            raw = res.stdout.strip()
            if raw:
                return [line.strip().lower() for line in raw.split("\n") if line.strip()]
        except Exception as e:
            logger.warning("Could not query %s open tabs: %s", browser_name, e)
        return []

    @classmethod
    def launch_workspace(cls, config: Dict[str, Any]) -> None:
        """Opens Antigravity, Google Chrome, and Brave Browser without duplicating existing tabs."""
        apps_cfg = config.get("startup_apps", {})
        if not apps_cfg.get("enabled", True):
            return

        logger.info("Initializing startup workspace applications with duplicate checks...")

        # 1. Antigravity IDE
        if apps_cfg.get("open_antigravity", True):
            logger.info("Opening Antigravity IDE...")
            subprocess.Popen(["/usr/bin/open", "-a", "Antigravity IDE"])

        # 2. Google Chrome (Microsoft Teams)
        if apps_cfg.get("open_chrome", True):
            teams_url = apps_cfg.get("teams_url", "https://teams.microsoft.com")
            profile_dir = apps_cfg.get("chrome_profile_directory", "Default")

            # Check if Teams is already open in Chrome
            chrome_tabs = cls._get_open_urls("Google Chrome")
            teams_already_open = any("teams.microsoft.com" in url for url in chrome_tabs)

            if teams_already_open:
                logger.info("Microsoft Teams is already open in Google Chrome. Focusing window.")
                subprocess.Popen(["/usr/bin/open", "-a", "Google Chrome"])
            else:
                logger.info("Opening Microsoft Teams in Google Chrome...")
                if profile_dir:
                    subprocess.Popen([
                        "/usr/bin/open", "-a", "Google Chrome",
                        "--args", f"--profile-directory={profile_dir}", teams_url
                    ])
                else:
                    subprocess.Popen(["/usr/bin/open", "-a", "Google Chrome", teams_url])

        # 3. Brave Browser (Spotify & YouTube Music)
        if apps_cfg.get("open_brave", True):
            target_urls = apps_cfg.get("brave_urls", [
                "https://open.spotify.com",
                "https://music.youtube.com"
            ])

            # Check existing Brave tabs
            brave_tabs = cls._get_open_urls("Brave Browser")
            urls_to_open = []

            for target in target_urls:
                target_domain = target.replace("https://", "").replace("http://", "").split("/")[0]
                already_open = any(target_domain in tab for tab in brave_tabs)
                if already_open:
                    logger.info("Tab '%s' is already open in Brave Browser. Skipping.", target)
                else:
                    urls_to_open.append(target)

            if urls_to_open:
                logger.info("Opening missing tabs in Brave Browser: %s", urls_to_open)
                subprocess.Popen(["/usr/bin/open", "-a", "Brave Browser", *urls_to_open])
            else:
                logger.info("All requested tabs already open in Brave Browser. Focusing window.")
                subprocess.Popen(["/usr/bin/open", "-a", "Brave Browser"])
