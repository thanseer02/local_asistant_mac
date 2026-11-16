import ctypes
import os
import select
import subprocess
import time
from datetime import datetime

# Load macOS libSystem for notify(3) APIs
lib = ctypes.cdll.LoadLibrary('/usr/lib/libSystem.B.dylib')

# Female voice: "Samantha" is the high-quality built-in macOS female voice
VOICE = "Moira"

def get_greeting(hour=None):
    if hour is None:
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning, Sir. Welcome back! Wishing you a productive day ahead."
    elif 12 <= hour < 17:
        return "Good afternoon, Sir. I hope your day is progressing well."
    elif 17 <= hour < 21:
        return "Good evening, Sir. Welcome back! Ready to continue where we left off?"
    else:
        return "Working late, Sir? I hope everything is going smoothly. Remember to take a break and get some rest."

def speak(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Speaking: {message}", flush=True)
    subprocess.run(["/usr/bin/say", "-v", VOICE, message])

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
    COOLDOWN_SECONDS = 10  # Prevent double trigger if both screensaver and unlock fire together

    print("Assistant is running and waiting for screensaver/unlock events...", flush=True)

    while True:
        try:
            rlist, _, _ = select.select(list(fd_map.keys()), [], [], 60)
            now = time.time()

            for fd in rlist:
                # Read the notification token from the descriptor to clear it
                os.read(fd, 4)
                event_name = fd_map.get(fd, "unknown")

                if now - last_spoken_time > COOLDOWN_SECONDS:
                    last_spoken_time = now
                    print(f"Detected event: {event_name}", flush=True)
                    # Short pause so audio starts when screen is awake
                    time.sleep(1)
                    speak(get_greeting())

        except KeyboardInterrupt:
            print("Stopping assistant listener.", flush=True)
            break
        except Exception as e:
            print(f"Error in event loop: {e}", flush=True)
            time.sleep(2)

def main():
    # Initial greeting upon starting/login
    speak(get_greeting())
    # Keep running in background to listen for screensaver exit and unlock events
    listen_for_events()

if __name__ == "__main__":
    main()






