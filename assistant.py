import ctypes
import json
import os
import select
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Path to config file
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

DEFAULT_CONFIG = {
    "voice": "Moira",
    "login_delay_seconds": 2,
    "cooldown_seconds": 3,
    "user_title": "Sir",
    "greetings": {
        "morning": "Good morning, {title}. Welcome back! Wishing you a productive day ahead.",
        "afternoon": "Good afternoon, {title}. I hope your day is progressing well.",
        "evening": "Good evening, {title}. Welcome back! Ready to continue where we left off?",
        "night": "Working late, {title}? I hope everything is going smoothly. Remember to take a break and get some rest."
    }
}

def load_config():
    """Load settings from config.json, with automatic fallback to defaults."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            print(f"Warning: Failed to parse config.json ({e}). Using defaults.", flush=True)
    return DEFAULT_CONFIG

# Load macOS libSystem for notify(3) APIs
lib = ctypes.cdll.LoadLibrary('/usr/lib/libSystem.B.dylib')

def get_greeting(config, hour=None):
    if hour is None:
        hour = datetime.now().hour

    title = config.get("user_title", "Sir")
    greetings = config.get("greetings", DEFAULT_CONFIG["greetings"])

    if 5 <= hour < 12:
        template = greetings.get("morning", DEFAULT_CONFIG["greetings"]["morning"])
    elif 12 <= hour < 17:
        template = greetings.get("afternoon", DEFAULT_CONFIG["greetings"]["afternoon"])
    elif 17 <= hour < 21:
        template = greetings.get("evening", DEFAULT_CONFIG["greetings"]["evening"])
    else:
        template = greetings.get("night", DEFAULT_CONFIG["greetings"]["night"])

    return template.format(title=title)

def speak(message, config):
    voice = config.get("voice", "Moira")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speaking with voice '{voice}': {message}", flush=True)
    subprocess.run(["/usr/bin/say", "-v", voice, message])

def listen_for_events():
    """
    Listens for macOS system notifications:
    - com.apple.screensaver.didstop: user dismissed screensaver
    - com.apple.screenIsUnlocked: user unlocked the screen
    """
    events = [
        b'com.apple.screensaver.didstop',
        b'com.apple.screenIsUnlocked',
    ]

    fd_map = {}
    tokens = []

    for event in events:
        fd = ctypes.c_int()
        token = ctypes.c_int()
        status = lib.notify_register_file_descriptor(event, ctypes.byref(fd), 0, ctypes.byref(token))
        if status == 0 and fd.value >= 0:
            fd_map[fd.value] = event.decode('utf-8')
            tokens.append(token)
            print(f"Registered listener for: {event.decode('utf-8')}", flush=True)
        else:
            print(f"Failed to register for: {event.decode('utf-8')}, status: {status}", flush=True)

    if not fd_map:
        print("No event listeners could be registered. Exiting listener loop.", flush=True)
        return

    last_spoken_time = 0
    print("Assistant is running and waiting for screensaver/unlock events...", flush=True)

    while True:
        try:
            rlist, _, _ = select.select(list(fd_map.keys()), [], [], 60)
            now = time.time()

            # Reload config dynamically so edits take effect without restarting
            config = load_config()
            cooldown = config.get("cooldown_seconds", 3)
            delay = config.get("login_delay_seconds", 2)

            for fd in rlist:
                os.read(fd, 4)
                event_name = fd_map.get(fd, "unknown")

                if now - last_spoken_time > cooldown:
                    last_spoken_time = now
                    print(f"Detected event: {event_name}", flush=True)
                    time.sleep(delay)
                    speak(get_greeting(config), config)

        except KeyboardInterrupt:
            print("Stopping assistant listener.", flush=True)
            break
        except Exception as e:
            print(f"Error in event loop: {e}", flush=True)
            time.sleep(2)

def main():
    config = load_config()
    # Initial greeting upon starting/login
    speak(get_greeting(config), config)
    # Background event loop
    listen_for_events()

if __name__ == "__main__":
    main()
