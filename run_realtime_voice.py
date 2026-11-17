#!/usr/bin/env python3
"""
CLI entry point to launch the Realtime Conversational Voice Assistant (ChatGPT Voice style).
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from modules.services.logging_service import logger
from modules.voice.voice_controller import RealtimeVoiceController


async def main():
    settings = get_settings()

    if not settings.realtime.api_key:
        print("\n" + "=" * 60)
        print("  [!] OpenAI API Key Not Found")
        print("=" * 60)
        print("Please export your OpenAI API key or add it to a .env file:")
        print("  export OPENAI_API_KEY='sk-...'")
        print("or create a .env file with:")
        print("  OPENAI_API_KEY=sk-...\n")
        key = input("Enter OPENAI_API_KEY now (or press Enter to exit): ").strip()
        if not key:
            sys.exit(1)
        os.environ["OPENAI_API_KEY"] = key
        settings.realtime.api_key = key

    controller = RealtimeVoiceController(settings=settings)
    try:
        await controller.start_session()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Session interrupted by user.")
    finally:
        await controller.stop_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession exited.")
