# 🎙️ MacAssistant

An intelligent, lightweight background voice daemon for macOS inspired by Marvel's **J.A.R.V.I.S.** and **F.R.I.D.A.Y.**.

MacAssistant monitors low-level macOS kernel events and schedules to deliver natural, time-aware audio briefings, health reminders, and automated workspace launches with **zero external dependencies** and **~0% CPU usage**.

---

## ✨ Features

- 🦸 **Marvel Personas**:
  - **J.A.R.V.I.S.**: Articulate, polite British butler cadence (`Daniel` voice).
  - **F.R.I.D.A.Y.**: Warm, conversational Irish voice (`Moira` voice).
- 🔊 **Iron Man HUD UI Chimes**: Plays an authentic Marvel sci-fi UI upward chime (`hud_chime.wav`) before speaking.
- ⚡ **Low-Latency Wake Detection**: Instant (<0.5s) greeting on login, screen unlock (Touch ID/password), and screensaver exit via `notify(3)`.
- 🌅 **Morning & Login Intelligence Briefing**:
  - Live local weather (without external API keys).
  - Configurable calendar & task briefings (`include_calendar` can be toggled on/off).
  - 💻 **Developer Git Inspector**: Summarizes uncommitted files and unpushed commits across your active projects.
- 🚀 **Smart Workspace Launcher**:
  - Launches Antigravity IDE, Google Chrome (Teams), and Brave (Spotify + YouTube Music).
  - **Duplicate Prevention**: Detects existing open tabs in Chrome and Brave so it never duplicates tabs.
- 🌿 **Health & Ergonomic Alerts (Exactly-Once Engine)**:
  - **20-20-20 Rule**: Prompts a 20-second distant look every 20 minutes to prevent eye fatigue.
  - **Hydration**: Reminds you to drink water with random 30–45 minute jitter (work hours only, Mon–Fri).
  - **Late-Night Work Guardian**: Prompts you every 30 minutes between 10:00 PM and 5:00 AM (midnight-crossing window).
  - **Atomic State Persistence**: Guaranteed exactly-once execution via `scheduler_state.json`. Prevents duplicate alerts and caps sleep/wake recovery at 1 single reminder.
- ⏰ **Daily Schedule Alerts**: Pre-set reminders for morning tea (11:00 AM), lunch (1:00 PM), afternoon tea (4:00 PM), and end of day (6:18 PM). Never repeats on the same day even across daemon restarts.
- 🛑 **Shutdown / Logout Farewell**: Catches system `SIGTERM` on shutdown or restart to bid a polite farewell before powering down.
- 🔄 **Live Hot-Reloading**: Any edit in `config.json` takes effect immediately without needing to restart the daemon.
- ⚡ **Prioritized Speech Queue & Barge-In**: Thread-safe priority queue (`URGENT > BRIEFING > REMINDER > NORMAL`) with automatic stale reminder dropping (>60s) and instant interruption.
- 🛡️ **Meeting & Focus Suppression (`FocusGuard`)**: Automatically suppresses and defers non-urgent speech when in Teams, Zoom, Webex, Google Meet, or macOS Focus/Do Not Disturb mode.
- 🎙️ **Zero-Degradation Push-to-Talk**: Native Swift on-device speech input helper. Mic opens strictly on trigger and terminates immediately after utterance, completely preserving Bluetooth headphones high-fidelity A2DP stereo.
- 🧠 **Persistent SQLite Memory Store**: Zero-dependency SQLite store (`~/Library/Application Support/MacAssistant/memory.db`) supporting "remember that", "what do you remember about", and "forget".
- 🧩 **Pluggable Skills Registry**: Auto-discovering skills plugin framework supporting Apple Shortcuts (`shortcuts run`), Spotify/Music media playback, and system health queries.

---

## 🏛️ Project Architecture

```text
MacAssistant/
├── assistant.py                   # Clean LaunchAgent entry point
├── config.json                    # Configuration (personas, voices, timings, apps)
├── README.md                      # Documentation & setup guide
├── voices.text                    # Curated voice preview commands
├── venv/                          # Local Python virtual environment
├── sounds/
│   └── hud_chime.wav              # Synthesized Iron Man HUD audio cue
├── tests/                         # Pure standard-library test suite
│   ├── test_assistant_core.py     # Core regression & priority queue tests
│   └── test_scheduler_strict.py   # Exactly-once & monotonic scheduler tests
└── mac_assistant/                 # Core Architecture Package
    ├── __init__.py                # Package root
    ├── config_manager.py          # Hot-reloading & safe JSON fallback
    ├── voice_engine.py            # Prioritized speech queue, HUD player & barge-in
    ├── event_listener.py          # Low-level macOS notify(3) kernel listener
    ├── scheduler.py               # Monotonic & atomic reminder scheduler
    ├── app_launcher.py            # App & browser workspace launcher with deduplication
    ├── briefing_service.py        # Concurrent weather & calendar integration
    ├── focus_guard.py             # Focus & active meeting audio suppression
    ├── memory_store.py            # SQLite long-term memory store
    ├── git_inspector.py           # Developer repository status checker
    ├── skills/                    # Pluggable skills registry
    └── daemon.py                  # Core event loop coordinating all layers
```

---

## 📦 Setting Up on Another Mac (Step-by-Step)

Follow these simple steps to install and run MacAssistant on any new Mac:

### Prerequisites
- macOS Monterey, Ventura, Sonoma, or Sequoia.
- Python 3.9+ (pre-installed on macOS or via Xcode command line tools).

---

### Step 1: Clone or Copy the Repository

Copy the `MacAssistant` project folder to your new Mac (for example, into `~/Documents/MacAssistant`):

```bash
cd ~/Documents
# If using git:
# git clone <your-repo-url> MacAssistant
cd MacAssistant
```

---

### Step 2: Create the Python Virtual Environment

```bash
python3 -m venv venv
```
*(No `pip install` required! MacAssistant uses pure standard library and native macOS frameworks.)*

---

### Step 3: Configure `config.json` for the New Mac

Open [config.json](file:///Users/tanseer/Documents/oopsss/MacAssistant/config.json) and verify your paths:

1. **User Name**: Set `"user_name": "Sir"` or `"Boss"`.
2. **Git Repositories**: Update `"git_briefing" -> "repositories"` with the absolute paths to your code projects on the new machine:
   ```json
   "git_briefing": {
     "enabled": true,
     "repositories": [
       "/Users/YOUR_USERNAME/Documents/MacAssistant",
       "/Users/YOUR_USERNAME/Documents/my-other-project"
     ]
   }
   ```
3. **Startup Apps**: If you don't use Brave or Chrome on the new Mac, you can toggle them under `"startup_apps"`.

---

### Step 4: Create the LaunchAgent Plist File

macOS uses LaunchAgents to run your assistant automatically in the background on startup.

1. Ensure the LaunchAgents directory exists:
   ```bash
   mkdir -p ~/Library/LaunchAgents
   ```

2. Create `~/Library/LaunchAgents/com.personal.macassistant.plist`:
   ```bash
   nano ~/Library/LaunchAgents/com.personal.macassistant.plist
   ```

3. Paste the following configuration (replace `YOUR_USERNAME` and ensure the path points to your `MacAssistant` folder):

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
        <string>/Users/YOUR_USERNAME/Documents/MacAssistant/venv/bin/python</string>
        <string>/Users/YOUR_USERNAME/Documents/MacAssistant/assistant.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/Documents/MacAssistant</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <!-- Allows time for goodbye farewell speech during system shutdown -->
    <key>ExitTimeOut</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>/tmp/macassistant.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/macassistant-error.log</string>
</dict>
</plist>
```

---

### Step 5: Start the Daemon

Load and start the service via macOS `launchctl`:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist
```
*(Or alternatively: `launchctl load -w ~/Library/LaunchAgents/com.personal.macassistant.plist`)*

---

### Step 6: Verify Everything is Working

1. **Check process status**:
   ```bash
   launchctl list | grep com.personal.macassistant
   ```
   *(You should see an active PID)*

2. **Check the logs**:
   ```bash
   cat /tmp/macassistant-error.log
   ```

3. **Lock and unlock your Mac**:
   Press <kbd>Cmd</kbd> + <kbd>Ctrl</kbd> + <kbd>Q</kbd> to lock your Mac, then unlock it with Touch ID or your password. You will hear the HUD chime followed by your assistant!

---

## 🛠️ Everyday Service Controls & Commands

You can control the background daemon directly from your terminal using macOS `launchctl`:

### 🔄 Restart Assistant
```bash
launchctl bootout gui/$(id -u)/com.personal.macassistant 2>&1; sleep 1; launchctl enable gui/$(id -u)/com.personal.macassistant && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist
```

### 🟢 Start Assistant
```bash
launchctl enable gui/$(id -u)/com.personal.macassistant && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist
```

### 🛑 Stop Assistant
```bash
launchctl bootout gui/$(id -u)/com.personal.macassistant
```

### 🔍 Check Process & Status
```bash
launchctl list | grep macassistant
```
*(If running, it outputs `<PID> 0 com.personal.macassistant`)*

### 📜 Stream Realtime Logs
```bash
tail -f /tmp/macassistant-error.log
```

### 🧪 Run Manually in Terminal (Interactive Debug Mode)
```bash
source venv/bin/activate && python assistant.py
```

### 🧪 Run Strict Unit Test Suite
```bash
python3 -m unittest discover tests
```

---

### Quick Reference Table

| Action | One-Liner Command |
| :--- | :--- |
| **Restart Service** | `launchctl bootout gui/$(id -u)/com.personal.macassistant 2>&1; sleep 1; launchctl enable gui/$(id -u)/com.personal.macassistant && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist` |
| **Start Service** | `launchctl enable gui/$(id -u)/com.personal.macassistant && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist` |
| **Stop Service** | `launchctl bootout gui/$(id -u)/com.personal.macassistant` |
| **Check Status** | `launchctl list \| grep macassistant` |
| **View Live Logs** | `tail -f /tmp/macassistant-error.log` |
| **Run Tests** | `python3 -m unittest discover tests` |
| **Test Interactively** | `source venv/bin/activate && python assistant.py` |

---

## 🎭 Switching Personas & Voices

Open `config.json` and change `"assistant_persona"`:
- Set `"assistant_persona": "jarvis"` for Paul Bettany's British butler style.
- Set `"assistant_persona": "friday"` for Kerry Condon's Irish AI style.

Changes reload automatically—no restart needed!
