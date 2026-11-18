#!/usr/bin/env python3
"""
MacAssistant Entry Point.
Runs the background daemon service.
Supports CLI overrides:
  --reroll: Forces rolling a new persona for the current session.
  --persona <id>: Forces launching with a specific persona.
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.daemon import AssistantDaemon
from mac_assistant.personality import personality_engine
from mac_assistant.config_manager import ConfigManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MacAssistant Voice Daemon")
    parser.add_argument("--reroll", action="store_true", help="Force reroll persona on launch")
    parser.add_argument("--persona", type=str, default=None, help="Force specific persona ID (e.g. jarvis, friday, alfred, coach, zen, pirate, noir, sarcastic, sleepy)")
    args = parser.parse_args()

    config = ConfigManager.load()
    if args.reroll or args.persona:
        personality_engine.initialize_session(config, force_reroll=args.reroll, force_persona=args.persona)

    daemon = AssistantDaemon()
    daemon.start()
