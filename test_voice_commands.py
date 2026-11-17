#!/usr/bin/env python3
"""Interactive test script for voice commands & wake-words."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mac_assistant.command_dispatcher import VoiceCommandDispatcher
from mac_assistant.config_manager import ConfigManager
from mac_assistant.voice_engine import VoiceEngine


def test_command(cmd_text: str):
    print(f"\n🎤 User Said: \"{cmd_text}\"")
    cfg = ConfigManager.load()
    engine = VoiceEngine()
    persona = cfg.get("assistant_persona", "friday")

    success, reply = VoiceCommandDispatcher.execute_command(cmd_text, persona=persona)
    print(f"🤖 Assistant Reply: {reply}")
    engine.speak(reply, cfg)


def main():
    print("=" * 60)
    print("🎙️ MacAssistant Voice Command Tester")
    print("=" * 60)
    print("Type a command (or choose a number) to hear the assistant execute and reply:")
    print("1. lock my mac")
    print("2. open vs code")
    print("3. open chrome")
    print("4. what time is my next meeting")
    print("5. take a quick note finish MacAssistant testing")
    print("6. volume up")
    print("q. quit\n")

    test_map = {
        "1": "lock my mac",
        "2": "open vs code",
        "3": "open chrome",
        "4": "what time is my next meeting",
        "5": "take a quick note finish MacAssistant testing",
        "6": "volume up",
    }

    while True:
        try:
            choice = input("Enter choice or text [1-6/text/q]: ").strip()
            if not choice or choice.lower() in ["q", "quit", "exit"]:
                print("Exiting test.")
                break

            cmd = test_map.get(choice, choice)
            test_command(cmd)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break


if __name__ == "__main__":
    main()
