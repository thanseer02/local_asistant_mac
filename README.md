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
  - Apple Reminders / Calendar task overview.
  - 💻 **Developer Git Inspector**: Summarizes uncommitted files and unpushed commits across your active projects.
- 🚀 **Smart Workspace Launcher**:
  - Launches Antigravity IDE, Google Chrome (Teams), and Brave (Spotify + YouTube Music).
  - **Duplicate Prevention**: Detects existing open tabs in Chrome and Brave so it never duplicates tabs.
- 🌿 **Health & Ergonomic Alerts**:
  - **20-20-20 Rule**: Prompts a 20-second distant look every 20 minutes to prevent eye fatigue.
  - **Hydration**: Reminds you to drink water every 45 minutes.
  - **Late-Night Work Guardian**: Prompts you every 30 minutes between 10:00 PM and 5:00 AM to take rest.
- ⏰ **Daily Schedule Alerts**: Pre-set reminders for morning tea (11:00 AM), lunch (1:00 PM), afternoon tea (4:00 PM), and end of day (6:18 PM).
- 🛑 **Shutdown / Logout Farewell**: Catches system `SIGTERM` on shutdown or restart to bid a polite farewell before powering down.
- 🔄 **Live Hot-Reloading**: Any edit in `config.json` takes effect immediately without needing to restart the daemon.

---

## 🏛️ Project Architecture

```text
MacAssistant/
├── assistant.py                   # Clean LaunchAgent entry point
├── config.json                    # Configuration (personas, voices, timings, apps, voice commands)
├── test_voice_system.py           # Interactive test CLI for voice commands & mic testing
├── README.md                      # Documentation & setup guide
├── voices.text                    # Curated voice preview commands
├── venv/                          # Local Python virtual environment
├── sounds/
│   └── hud_chime.wav              # Synthesized Iron Man HUD audio cue
└── mac_assistant/                 # Core Architecture Package
    ├── __init__.py                # Package root
    ├── config_manager.py          # Hot-reloading & safe JSON fallback
    ├── voice_engine.py            # Personas, HUD audio player & speech synthesis
    ├── speech_output.py           # Speech output service wrapping macOS /usr/bin/say & afplay
    ├── microphone_service.py      # Thread-safe microphone capture, silence detection & anti-loop guard
    ├── speech_recognizer.py       # Offline / online speech-to-text transcription service
    ├── command_router.py          # Intent routing & natural speech phrasing normalization
    ├── application_launcher_service.py # Allowlisted, safe application launch service
    ├── file_search.py             # Spotlight & filesystem search for Flutter projects & PDFs
    ├── voice_controller.py        # Central voice orchestration with lifecycle management
    ├── event_listener.py          # Low-level macOS notify(3) kernel listener
    ├── scheduler.py               # Health & time-of-day alert scheduler
    ├── app_launcher.py            # App & browser workspace launcher with deduplication
    ├── briefing_service.py        # Morning weather & calendar integration
    ├── git_inspector.py           # Developer repository status checker
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

## 🛠️ Everyday Service Controls

| Action | Command |
| :--- | :--- |
| **Start Service** | `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist` |
| **Stop Service** | `launchctl bootout gui/$(id -u)/com.personal.macassistant` |
| **Restart Service** | `launchctl bootout gui/$(id -u)/com.personal.macassistant && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.personal.macassistant.plist` |
| **View Live Logs** | `tail -f /tmp/macassistant-error.log` |
| **Test Interactively** | `source venv/bin/activate && python assistant.py` |

---

## 🎙️ Natural Voice Commands & Controls

MacAssistant includes a modular, safe voice-command engine with silence detection and speech-to-text.

### Supported Natural Voice Commands

| Intent / Action | Example Voice Phrasings | System Behavior |
| :--- | :--- | :--- |
| **Open Chrome** | *"open Google Chrome"*, *"launch Chrome"*, *"open browser"* | Launches Chrome safely using `/usr/bin/open -a` |
| **Open VS Code** | *"open visual studio code"*, *"open vs code"*, *"launch vscode"* | Launches VS Code via allowlist |
| **Open Terminal** | *"open terminal"*, *"launch terminal console"* | Launches macOS Terminal |
| **Search Flutter Projects** | *"find flutter projects"*, *"search flutter"*, *"where is my flutter app"* | Searches Spotlight & filesystem for directories containing `pubspec.yaml` |
| **Search PDF Documents** | *"search pdf files"*, *"find pdf resume"*, *"look for invoices pdf"* | Finds `.pdf` files matching keywords |
| **Check Date & Time** | *"what time is it"*, *"what is the date today"*, *"current time"* | Speaks the current time and day |
| **Stop Listening** | *"stop listening"*, *"pause voice"*, *"mute microphone"* | Pauses voice listening thread cleanly |
| **Exit / Shutdown** | *"exit assistant"*, *"quit assistant"*, *"power down"* | Performs safe shutdown sequence |

### Testing Voice Commands Interactively

You can test both text command dispatch and live microphone listening using `test_voice_system.py`:

```bash
# 1. Text Simulation Mode (Test routing and responses without speaking)
source venv/bin/activate
./test_voice_system.py --sim

# 2. Live Microphone Mode (Test PyAudio capture & silence detection)
./test_voice_system.py --mic
```

---

## 🔒 macOS Microphone Permissions & Setup

Because Apple Silicon Macs (like Mac mini) require microphone authorization:
1. Open **System Settings** → **Privacy & Security** → **Microphone**.
2. Verify that **Terminal** (or your Python environment / iTerm) is toggled to **ON**.
3. If using a Bluetooth headset (such as `WH-CH510`) or USB microphone, MacAssistant automatically discovers and binds to it.

---

## 🎭 Switching Personas & Voices

Open `config.json` and change `"assistant_persona"`:
- Set `"assistant_persona": "jarvis"` for Paul Bettany's British butler style.
- Set `"assistant_persona": "friday"` for Kerry Condon's Irish AI style.

Changes reload automatically—no restart needed!
