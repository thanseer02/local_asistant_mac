"""Main daemon loop coordinating events, scheduler, and voice synthesis."""

import logging
import os
import select
import signal
import sys
import time
from datetime import datetime

from .app_launcher import AppLauncher
from .briefing_service import BriefingService
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
        self._is_shutting_down: bool = False

        # Register termination signal handlers for shutdown / reboot / logout
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame) -> None:
        """Invoked when macOS sends SIGTERM during system shutdown or logout."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("System shutdown/termination signal received (%s). Saying goodbye...", signum)

        try:
            config = ConfigManager.load()
            farewell = self.engine.get_goodbye(config)
            self.engine.speak(farewell, config)
        except Exception as e:
            logger.error("Error during shutdown farewell: %s", e)
        finally:
            sys.exit(0)

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

        # Initial login greeting with optional Morning Briefing
        greeting = self.engine.get_greeting(config)
        briefing = BriefingService.generate_morning_briefing(config)
        full_initial_speech = f"{greeting} {briefing}".strip()
        self.engine.speak(full_initial_speech, config)
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

                # 1. Check Fixed Schedule & Wellness Reminders
                if self.scheduler.check_scheduled(config, current_time_str):
                    self.last_spoken_time = time.time()

                if self.scheduler.check_eye_break(config, now):
                    self.last_spoken_time = time.time()

                if self.scheduler.check_hydration(config, now):
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
