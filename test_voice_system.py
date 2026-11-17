#!/usr/bin/env python3
"""Interactive test script for MacAssistant modular voice command system."""

import sys
import time
from mac_assistant.config_manager import ConfigManager
from mac_assistant.speech_output import SpeechOutputService
from mac_assistant.voice_controller import VoiceController

def main():
    print("=" * 60)
    print("       MacAssistant Modular Voice System Test")
    print("=" * 60)
    
    config = ConfigManager.load()
    output_service = SpeechOutputService()
    
    def on_exit():
        print("[!] Voice Controller requested exit. Shutting down test.")
        sys.exit(0)

    controller = VoiceController(
        config=config,
        speech_output=output_service,
        on_exit_requested=on_exit
    )
    
    print("\n[Modes Available]")
    print("1. Text Simulation Mode (Type commands to test routing, safety, & speech)")
    print("2. Live Microphone Listening Mode (Tests PyAudio, silence detection, & recognition)")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--mic":
        choice = "2"
    elif len(sys.argv) > 1 and sys.argv[1] == "--sim":
        choice = "1"
    else:
        try:
            choice = input("\nSelect mode (1 or 2, default 1): ").strip() or "1"
        except EOFError:
            choice = "1"
            
    if choice == "1":
        print("\n--- TEXT SIMULATION MODE ---")
        print("Type natural voice commands. Examples:")
        print("  - 'open chrome'")
        print("  - 'launch vs code'")
        print("  - 'open terminal'")
        print("  - 'find flutter projects'")
        print("  - 'search pdf'")
        print("  - 'what time is it'")
        print("  - 'stop listening'")
        print("  - 'exit' (to quit)")
        print("-" * 40)
        
        while True:
            try:
                line = input("\nUtterance > ").strip()
                if not line:
                    continue
                controller.process_command(line)
            except (KeyboardInterrupt, EOFError):
                print("\nExiting simulation.")
                break
    else:
        print("\n--- LIVE MICROPHONE CAPTURE MODE ---")
        print("Attempting to connect to microphone...")
        started = controller.start()
        if not started:
            print("[x] Failed to start microphone listener. Check permissions or devices.")
            return
            
        print("[+] Listening in background... Speak into your microphone.")
        print("Press Ctrl+C to terminate.")
        try:
            while controller.is_listening:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping listener...")
            controller.stop()
            print("Done.")

if __name__ == "__main__":
    main()
