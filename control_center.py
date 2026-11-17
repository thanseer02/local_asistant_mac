#!/usr/bin/env python3
"""Launcher script for Friday/Jarvis macOS Desktop Control Center."""

import sys
from pathlib import Path

# Ensure MacAssistant root is on path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mac_assistant.gui.jarvis_main_window import launch_jarvis_app

if __name__ == "__main__":
    launch_jarvis_app()
