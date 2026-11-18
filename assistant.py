#!/usr/bin/env python3
"""
MacAssistant Entry Point.
Runs the background daemon service or system diagnostics.
"""

import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.daemon import AssistantDaemon
from mac_assistant.doctor import SystemDoctor
from mac_assistant.logging_config import setup_structured_logging

if __name__ == "__main__":
    if "--doctor" in sys.argv:
        SystemDoctor.print_report()
        sys.exit(0)

    setup_structured_logging()
    daemon = AssistantDaemon()
    daemon.start()
