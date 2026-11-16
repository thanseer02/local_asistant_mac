# MacAssistant

A lightweight background personal assistant for macOS that speaks greetings using a female voice (`Samantha`) on:
1. **System Login / Boot / Restart**
2. **Screen Saver Dismissal** (when you return to your Mac)
3. **Screen Unlock**

---

## How It Works

- **Voice**: Uses macOS's built-in natural female voice (`Samantha` via `/usr/bin/say -v Samantha`).
- **Events**: Listens efficiently to macOS system notification events (`com.apple.screensaver.didstop` and `com.apple.screenIsUnlocked`) with virtually 0% CPU consumption.
- **Debounce / Cooldown**: Includes a 10-second debounce window to prevent overlapping speech if both unlock and screensaver dismiss events fire at once.
- **Daemon (`KeepAlive`)**: Runs continuously as a LaunchAgent.

---

## Service Management (Start, Stop, Restart)

### 1. Apply Changes / Restart the Service

Whenever you update `assistant.py` or the plist, restart the agent:

```bash
launchctl bootout gui/$(id -u)/com.personal.macassistant
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist
```

---

### 2. Check Service Status

Verify that the process is running (you should see a PID number):
```bash
launchctl list | grep com.personal.macassistant
```

---

### 3. Stop / Unload the Service

To temporarily turn off the assistant:
```bash
launchctl bootout gui/$(id -u)/com.personal.macassistant
```

---

### 4. Monitor Live Logs

See when events fire and what is spoken:

```bash
# Watch output in real time
tail -f /tmp/macassistant.log

# Check for any errors
tail -f /tmp/macassistant-error.log
```

---

## Manual Test Run

You can test it directly in your terminal to hear the female voice and test dismissing your screensaver:

```bash
cd ~/Documents/oopsss/MacAssistant
source venv/bin/activate
python assistant.py
```

---

## Changing the Voice

If you want a different female voice (e.g., `Karen` [Australian], `Moira` [Irish], `Tessa` [South African]):
Edit `VOICE = "Samantha"` in [assistant.py](file:///Users/tanseer/Documents/oopsss/MacAssistant/assistant.py).
# local_asistant_mac
