"""Main daemon loop coordinating events, scheduler, and voice synthesis."""

import logging
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

from .app_launcher import AppLauncher
from .briefing_service import BriefingService
from .config_manager import ConfigManager
from .event_listener import NotificationListener
from .push_to_talk import PushToTalkController
from .scheduler import ReminderScheduler
from .skills.registry import SkillRegistry
from .voice_engine import SpeechPriority, VoiceEngine

logger = logging.getLogger("MacAssistant.Daemon")


class AssistantDaemon:
    """Core daemon managing system events and timed services."""

    def __init__(self):
        self.engine = VoiceEngine()
        self.listener = NotificationListener()
        self.scheduler = ReminderScheduler(self.engine)
        self.skills = SkillRegistry()
        self.ptt = PushToTalkController(on_command_callback=self._handle_ptt_command)
        self.last_spoken_time: float = 0
        self.has_launched_startup_apps: bool = False
        self._is_shutting_down: bool = False
        self._avatar_proc: Optional[subprocess.Popen] = None

        # Register termination signal handlers for shutdown / reboot / logout
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _ensure_avatar_running(self, config: Dict[str, Any]) -> None:
        """Launches or restarts the avatar overlay GUI process if enabled and dead."""
        avatar_cfg = config.get("avatar", {})
        if not avatar_cfg.get("enabled", True):
            if self._avatar_proc and self._avatar_proc.poll() is None:
                self._avatar_proc.terminate()
                self._avatar_proc = None
            return

        # Check if already running healthy
        if self._avatar_proc and self._avatar_proc.poll() is None:
            return

        # Launch avatar_overlay.py using venv python interpreter
        venv_python = sys.executable
        overlay_script = Path(__file__).resolve().parent.parent / "modules" / "ui" / "avatar_overlay.py"
        if not overlay_script.exists():
            return

        try:
            self._avatar_proc = subprocess.Popen(
                [venv_python, str(overlay_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Spawned avatar overlay process (PID %d)", self._avatar_proc.pid)
        except Exception as e:
            logger.warning("Failed to launch avatar overlay process: %s", e)

    def _handle_ptt_command(self, transcript: str) -> None:
        """Executes spoken command through the skills registry and speaks response."""
        from .avatar_client import AvatarClient
        AvatarClient.thinking()
        config = ConfigManager.load()
        persona = config.get("assistant_persona", "friday")
        result = self.skills.dispatch(transcript, persona=persona, config=config)
        if not result.handled:
            AvatarClient.error()
        if result.response:
            self.engine.speak(result.response, config, priority=SpeechPriority.NORMAL)
            self.last_spoken_time = time.time()
        else:
            AvatarClient.idle()

    def _handle_shutdown(self, signum, frame) -> None:
        """Invoked when macOS sends SIGTERM during system shutdown or logout."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("System shutdown/termination signal received (%s). Saying goodbye...", signum)

        try:
            config = ConfigManager.load()
            farewell = self.engine.get_goodbye(config)
            self.engine.speak_farewell_and_wait(farewell, config, timeout=3.0)
        except Exception as e:
            logger.error("Error during shutdown farewell: %s", e)
        finally:
            from .avatar_client import AvatarClient
            AvatarClient.hide()
            if self._avatar_proc and self._avatar_proc.poll() is None:
                try:
                    self._avatar_proc.terminate()
                except Exception:
                    pass
            sys.exit(0)

    def start(self) -> None:
        """Starts the daemon loop."""
        if not self.listener.register():
            logger.error("Failed to register system notification listeners. Exiting.")
            return

        config = ConfigManager.load()
        self._ensure_avatar_running(config)

        # Launch startup workspace applications on initial session boot
        if not self.has_launched_startup_apps:
            AppLauncher.launch_workspace(config)
            self.has_launched_startup_apps = True

        # Initial login greeting with optional Morning Briefing
        greeting = self.engine.get_greeting(config)
        briefing = BriefingService.generate_morning_briefing(config)
        full_initial_speech = f"{greeting} {briefing}".strip()
        self.engine.speak(full_initial_speech, config, priority=SpeechPriority.BRIEFING)

        # Initialize event-driven scheduler heap
        self.scheduler.rebuild_schedule(config)
        logger.info("MacAssistant daemon started successfully.")

        last_config_check = time.time()

        while True:
            try:
                # Calculate sleep timeout: min(10s, seconds until next due event)
                timeout = self.scheduler.seconds_until_next_event(max_cap=10.0)

                # Sleep until next event or wake on unlock/screensaver kernel descriptor
                rlist, _, _ = select.select(self.listener.get_descriptors(), [], [], timeout)
                now = time.time()

                # Hot-reload config periodically or on loop iteration
                if now - last_config_check >= 5.0:
                    config = ConfigManager.load()
                    self._ensure_avatar_running(config)
                    last_config_check = now

                cooldown = config.get("cooldown_seconds", 3)
                delay = config.get("login_delay_seconds", 2)

                # 1. Process Due Scheduler Rules (20-20-20, hydration, meals, late-night)
                if self.scheduler.process_due_events(config):
                    self.last_spoken_time = time.time()

                # 2. Check Hardware / Session Unlock & Screensaver Events
                for fd in rlist:
                    os.read(fd, 4)  # Flush notification descriptor
                    event_name = self.listener.fd_map.get(fd, "unknown")

                    if now - self.last_spoken_time > cooldown:
                        self.last_spoken_time = now
                        logger.info("Detected event: %s", event_name)
                        # Re-sync schedule after system wake/unlock
                        self.scheduler.on_system_wake(config)
                        time.sleep(delay)

                        from .personality import personality_engine
                        is_quick, session_hours = personality_engine.record_unlock()
                        greeting_ctx = {
                            "name": config.get("user_name", "Sir"),
                            "quick_unlock": is_quick,
                            "session_hours": session_hours
                        }
                        greeting_text = self.engine.get_greeting(config, context=greeting_ctx)

                        # In morning or upon first unlock, append morning briefing
                        full_speech = greeting_text
                        if not is_quick:
                            briefing_text = BriefingService.generate_morning_briefing(config)
                            if briefing_text:
                                full_speech = f"{greeting_text} [[slnc 300]] {briefing_text}"

                        self.engine.speak(full_speech, config, priority=SpeechPriority.BRIEFING)

            except KeyboardInterrupt:
                logger.info("Assistant daemon stopped by user.")
                break
            except Exception as e:
                logger.error("Unexpected error in daemon loop: %s", e)
                time.sleep(2)
