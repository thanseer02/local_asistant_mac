# 🎙️ MacAssistant

An intelligent, lightweight macOS background daemon that greets you with natural speech whenever you:
- **Log in / Boot up / Restart** your Mac.
- **Dismiss the screen saver** (when you return to your desk).
- **Unlock your screen**.

Built with pure macOS system APIs (`notify(3)` via `libSystem` & `/usr/bin/say`), running with **zero third-party package dependencies** and **~0% CPU usage**.

---

## ✨ Features

- 🌅 **Time-Aware Greetings**: Context-sensitive messages for morning, afternoon, evening, and late-night work sessions.
- ⚡ **Instant Wake & Unlock Detection**: Listens to kernel notification events:
  - `com.apple.screensaver.didstop`
  - `com.apple.screenIsUnlocked`
- 🛡️ **Debounced Triggering**: Built-in 10-second cooldown prevents duplicate audio triggers when multiple system events fire simultaneously.
- 🗣️ **Configurable Voices**: Supports Siri, Samantha, Moira, Daniel (Jarvis-style), Rishi, and any installed macOS TTS voice.
- 🔄 **Background Daemon (`LaunchAgent`)**: Managed via macOS `launchctl` with automatic start-at-login and auto-restart on crash (`KeepAlive`).

---

## 📁 Project Structure

```text
MacAssistant/
├── config.json           # User configuration (voice, delays, greetings, title)
├── assistant.py          # Main daemon script & event listener
├── README.md             # Documentation & operational guide
├── voices.text           # Curated list of testable macOS voices
├── venv/                 # Local Python virtual environment
└── ~/Library/LaunchAgents/com.personal.macassistant.plist  # System service definition
```

---

## 🚀 Quick Setup & Installation

### 1. Ensure Python Virtual Environment is Ready

From this project directory:
```bash
python3 -m venv venv
```

### 2. Configure the LaunchAgent Plist

Create or verify the LaunchAgent plist at `~/Library/LaunchAgents/com.personal.macassistant.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.personal.macassistant</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/tanseer/Documents/oopsss/MacAssistant/venv/bin/python</string>
        <string>/Users/tanseer/Documents/oopsss/MacAssistant/assistant.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/tanseer/Documents/oopsss/MacAssistant</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/macassistant.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/macassistant-error.log</string>
</dict>
</plist>
```

### 3. Load & Start the Service

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist
```

---

## 🛠️ Service Management

### Check Status
Check if the service is registered and running (it should display a PID):
```bash
launchctl list | grep com.personal.macassistant
```

### Restart Service (After Code or Voice Changes)
```bash
launchctl bootout gui/$(id -u)/com.personal.macassistant
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist
```

### Stop / Disable Service
```bash
launchctl bootout gui/$(id -u)/com.personal.macassistant
```

---

## 📜 Logs & Debugging

Check live logs to see events and speech output:

```bash
# View live speech logs
tail -f /tmp/macassistant.log

# View errors (if any)
tail -f /tmp/macassistant-error.log
```

---

## 🗣️ Choosing & Testing Voices

To change the voice, modify line 12 in `assistant.py`:
```python
VOICE = "Samantha"  # or "Moira", "Daniel", "Karen", etc.
```

### Preview Voices in Terminal

You can audition voices directly from your terminal:

#### 👩 Female Voices
```bash
# Original Siri Voice (US)
say -v "Samantha" "Good evening, Sir. Welcome back!"

# Irish (Melodic & Friendly)
say -v "Moira" "Good evening, Sir. Welcome back!"

# Australian (Warm & Natural)
say -v "Karen" "Good evening, Sir. Welcome back!"

# Indian English
say -v "Lekha" "Good evening, Sir. Welcome back!"
```

#### 👨 Male Voices
```bash
# British English (Classic Jarvis / Butler style)
say -v "Daniel" "Good evening, Sir. Welcome back!"

# Indian English
say -v "Rishi" "Good evening, Sir. Welcome back!"

# American English (Deep Voice)
say -v "Ralph" "Good evening, Sir. Welcome back!"
```

> **Tip:** You can download enhanced/neural Siri voices under **System Settings** → **Accessibility** → **Spoken Content** → **Manage Voices...**.

---

## 🧪 Manual Terminal Test

To test the assistant directly without `launchctl`:

```bash
source venv/bin/activate
python assistant.py
```
Press `Ctrl + C` to stop.
