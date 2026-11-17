"""JARVIS Futuristic Top Status Bar widget."""

from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
from mac_assistant.gui.bridge_service import SystemStatus


class JarvisTopStatusBar(QFrame):
    """Futuristic Top Bar showing online status, time, mic, CPU/RAM, and active personality."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("jarvisTopBar")
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # 1. System Status Badge
        self.badge = QLabel("JARVIS ONLINE")
        self.badge.setObjectName("topBarStatusOnline")
        layout.addWidget(self.badge)

        # 2. Clock & Date
        self.clock_label = QLabel()
        self.clock_label.setObjectName("topBarMetrics")
        self.clock_label.setStyleSheet("color: #00e5ff; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(self.clock_label)

        layout.addStretch()

        # 3. Audio & Mic Telemetry
        self.mic_label = QLabel("MIC: ACTIVE (16kHz)")
        self.mic_label.setObjectName("topBarMetrics")
        layout.addWidget(self.mic_label)

        # 4. CPU & RAM
        self.metrics_label = QLabel("CPU: 0.0%  |  RAM: 0.0%")
        self.metrics_label.setObjectName("topBarMetrics")
        layout.addWidget(self.metrics_label)

        # 5. Active Profile
        self.profile_label = QLabel("PROFILE: JARVIS (DANIEL)")
        self.profile_label.setStyleSheet("color: #00ffaa; font-weight: 700; letter-spacing: 0.5px;")
        layout.addWidget(self.profile_label)

        self.update_clock()

    def update_clock(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%A, %B %d  •  %I:%M:%S %p"))

    def update_telemetry(self, status: SystemStatus):
        self.update_clock()
        if status.online:
            self.badge.setText(f"{status.active_persona.upper()} ONLINE")
            self.badge.setObjectName("topBarStatusOnline")
        else:
            self.badge.setText("OFFLINE")
            self.badge.setStyleSheet("color: #ff453a; border: 1px solid #ff453a; border-radius: 10px; padding: 3px 10px;")

        self.metrics_label.setText(f"CPU: {status.cpu_percent:.1f}%  |  RAM: {status.ram_percent:.1f}%")
        self.profile_label.setText(f"PROFILE: {status.active_persona.upper()} ({status.voice.upper()})")
