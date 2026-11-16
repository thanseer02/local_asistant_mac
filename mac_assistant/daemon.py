"""Main daemon loop coordinating events, scheduler, and voice synthesis."""

import logging
import os
import select
import time
from datetime import datetime

from .app_launcher import AppLauncher
from .config_manager import ConfigManager
from .event_listener import NotificationListener
from .scheduler import ReminderScheduler
from .voice_engine import VoiceEngine

logger = logging.getLogger("MacAssistant.Daemon")


class AssistantDaemon:
    """Core daemon managing system events and timed services."""

    def __init__(self):
        self.engine = VoiceEngine()
        self.listener = NotificationListener()
        self.scheduler = ReminderScheduler(self.engine)
        self.last_spoken_time: float = 0
        self.has_launched_startup_apps: bool = False

    def start(self) -> None:
        """Starts the daemon loop."""
        if not self.listener.register():
            logger.error("Failed to register system notification listeners. Exiting.")
            return

        config = ConfigManager.load()

        # Launch startup workspace applications on initial session boot
        if not self.has_launched_startup_apps:
            AppLauncher.launch_workspace(config)
            self.has_launched_startup_apps = True

        # Initial login greeting
        self.engine.speak(self.engine.get_greeting(config), config)
        logger.info("MacAssistant daemon started successfully.")

        while True:
            try:
                # Poll descriptors every 10 seconds or wake on unlock/screensaver event
                rlist, _, _ = select.select(self.listener.get_descriptors(), [], [], 10)
                now = time.time()
                now_dt = datetime.now()
                current_time_str = now_dt.strftime("%H:%M")

                # Dynamically reload configuration
                config = ConfigManager.load()
                cooldown = config.get("cooldown_seconds", 3)
                delay = config.get("login_delay_seconds", 2)

                # 1. Check Timed Reminders
                if self.scheduler.check_scheduled(config, current_time_str):
                    self.last_spoken_time = time.time()

                if self.scheduler.check_late_night(config, now_dt, now):
                    self.last_spoken_time = time.time()

                # 2. Check Hardware / Session Unlock & Screensaver Events
                for fd in rlist:
                    os.read(fd, 4)  # Flush notification descriptor
                    event_name = self.listener.fd_map.get(fd, "unknown")

                    if now - self.last_spoken_time > cooldown:
                        self.last_spoken_time = now
                        logger.info("Detected event: %s", event_name)
                        time.sleep(delay)
                        self.engine.speak(self.engine.get_greeting(config), config)

            except KeyboardInterrupt:
                logger.info("Assistant daemon stopped by user.")
                break
            except Exception as e:
                logger.error("Unexpected error in daemon loop: %s", e)
                time.sleep(2)
