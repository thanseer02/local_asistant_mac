import ctypes
import json
import os
import random
import select
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Path to config file
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

DEFAULT_CONFIG = {
    "voice": "Moira",
    "speech_rate": 180,
    "user_name": "Tanseer",
    "login_delay_seconds": 2,
    "cooldown_seconds": 3,
    "greetings": {
        "morning": [
            "Good morning, {name}! Hope you slept well. Ready to crush today?",
            "Hey {name}, morning! Coffee in hand? Let's get things rolling.",
            "Morning, {name}! Let's make today a great one.",
            "Good morning! Great to see you back at it, {name}."
        ],
        "afternoon": [
            "Hey {name}, welcome back! How's your day going so far?",
            "Good afternoon, {name}! Hope you're having a productive one.",
            "Welcome back, {name}! Ready to dive back into things?",
            "Hey {name}! Hope you took a quick breather. Let's keep the momentum going."
        ],
        "evening": [
            "Good evening, {name}! Hope you had a solid day.",
            "Hey {name}, welcome back! Ready to wrap up the day's work?",
            "Good evening, {name}! Let's knock out whatever is left on your list.",
            "Welcome back, {name}! Hope your evening is going well."
        ],
        "night": [
            "Still up, {name}? Make sure not to push yourself too hard tonight.",
            "Hey {name}, working late tonight? Remember to take a break and rest soon.",
            "Late night grind, {name}? I'm right here with you. Don't forget to hydrate.",
            "Working late, {name}? Hope things are going smoothly. Get some sleep when you can!"
        ]
    }
}

# Keep track of recent greeting to avoid back-to-back repeats
_last_chosen_greeting = None

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
    global _last_chosen_greeting

    if hour is None:
        hour = datetime.now().hour

    name = config.get("user_name") or config.get("user_title", "Tanseer")
    greetings = config.get("greetings", DEFAULT_CONFIG["greetings"])

    if 5 <= hour < 12:
        pool = greetings.get("morning", DEFAULT_CONFIG["greetings"]["morning"])
    elif 12 <= hour < 17:
        pool = greetings.get("afternoon", DEFAULT_CONFIG["greetings"]["afternoon"])
    elif 17 <= hour < 21:
        pool = greetings.get("evening", DEFAULT_CONFIG["greetings"]["evening"])
    else:
        pool = greetings.get("night", DEFAULT_CONFIG["greetings"]["night"])

    # If pool is a list, pick dynamically avoiding immediate repeat
    if isinstance(pool, list) and pool:
        candidates = [g for g in pool if g != _last_chosen_greeting] or pool
        chosen = random.choice(candidates)
        _last_chosen_greeting = chosen
        return chosen.format(name=name, title=name)
    elif isinstance(pool, str):
        return pool.format(name=name, title=name)

    return f"Welcome back, {name}!"

def speak(message, config):
    voice = config.get("voice", "Moira")
    rate = str(config.get("speech_rate", 180))
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speaking with voice '{voice}' (rate {rate}): {message}", flush=True)
    subprocess.run(["/usr/bin/say", "-v", voice, "-r", rate, message])

def listen_for_events():
    """
    Listens for macOS system notifications:
    - com.apple.screensaver.didstop: user dismissed screensaver
    - com.apple.screenIsUnlocked: screen unlocked (Touch ID / password)
    - com.apple.sessionDidUnlock: user session unlocked
    - com.apple.system.loginwindow.sessionDidUnlock: loginwindow session unlock
    """
    events = [
        b'com.apple.screensaver.didstop',
        b'com.apple.screenIsUnlocked',
        b'com.apple.sessionDidUnlock',
        b'com.apple.system.loginwindow.sessionDidUnlock',
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
