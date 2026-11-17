"""JARVIS Personal AI Control Center - Futuristic Desktop Application Window."""

import sys
from typing import Optional
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget
)

from mac_assistant.gui.bridge_service import AssistantBridgeService
from mac_assistant.gui.jarvis_dashboard import JarvisDashboardView
from mac_assistant.gui.jarvis_panels import (
    JarvisLiveAssistantView, JarvisProjectsView, JarvisSystemMonitorView
)
from mac_assistant.gui.jarvis_theme import JARVIS_FUTURISTIC_THEME
from mac_assistant.gui.jarvis_top_bar import JarvisTopStatusBar
from mac_assistant.gui.views import (
    ConversationHistoryView, PersonalityManagerView, SystemLogsView,
    ToolRegistryView
)


class JarvisControlCenterWindow(QMainWindow):
    """
    Futuristic macOS Desktop Control Center for JARVIS & FRIDAY:
    - Stark Industries / Iron Man aesthetic: Dark navy/black, cyan/electric blue accents, glassmorphic HUD.
    - Large animated circular Arc Reactor Core widget.
    - Top telemetry bar with live clock, status, microphone, and hardware stats.
    - Integrated panels: Dashboard, Live Assistant, Projects, System Monitor, History, Tools, Logs, Settings.
    """

    def __init__(self, bridge: Optional[AssistantBridgeService] = None):
        super().__init__()
        self.bridge = bridge or AssistantBridgeService()

        self.setWindowTitle("JARVIS — Personal AI Control Center")
        self.resize(1120, 750)
        self.setMinimumSize(920, 600)

        self._init_ui()
        self.setStyleSheet(JARVIS_FUTURISTIC_THEME)
        self._start_telemetry_loop()

    def _init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        main_vbox = QVBoxLayout(root)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 1. Top HUD Status Bar
        self.top_bar = JarvisTopStatusBar()
        main_vbox.addWidget(self.top_bar)

        # 2. Body: Sidebar + Dynamic Panel Stack
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("jarvisSidebar")
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 16)
        sb_lay.setSpacing(4)

        header = QLabel("⚡ J.A.R.V.I.S.", objectName="jarvisLogoHeader")
        sb_lay.addWidget(header)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_dash = self._create_nav_button("◈  Core Dashboard", 0)
        self.btn_live = self._create_nav_button("🎙️  Live Assistant", 1)
        self.btn_projects = self._create_nav_button("📁  Project Manager", 2)
        self.btn_telemetry = self._create_nav_button("⚡  System Monitor", 3)
        self.btn_history = self._create_nav_button("💬  Conversation Feed", 4)
        self.btn_tools = self._create_nav_button("🛠️  Automation & Tools", 5)
        self.btn_logs = self._create_nav_button("📜  Telemetry Logs", 6)
        self.btn_settings = self._create_nav_button("⚙️  Personality & Audio", 7)

        sb_lay.addWidget(self.btn_dash)
        sb_lay.addWidget(self.btn_live)
        sb_lay.addWidget(self.btn_projects)
        sb_lay.addWidget(self.btn_telemetry)
        sb_lay.addWidget(self.btn_history)
        sb_lay.addWidget(self.btn_tools)
        sb_lay.addWidget(self.btn_logs)
        sb_lay.addWidget(self.btn_settings)
        sb_lay.addStretch()

        body_layout.addWidget(self.sidebar)

        # Panels Stack
        self.stack = QStackedWidget()
        self.view_dash = JarvisDashboardView(self.bridge)
        self.view_live = JarvisLiveAssistantView(self.bridge)
        self.view_projects = JarvisProjectsView(self.bridge)
        self.view_telemetry = JarvisSystemMonitorView(self.bridge)
        self.view_history = ConversationHistoryView(self.bridge)
        self.view_tools = ToolRegistryView(self.bridge)
        self.view_logs = SystemLogsView(self.bridge)
        self.view_settings = PersonalityManagerView(self.bridge)

        self.stack.addWidget(self.view_dash)
        self.stack.addWidget(self.view_live)
        self.stack.addWidget(self.view_projects)
        self.stack.addWidget(self.view_telemetry)
        self.stack.addWidget(self.view_history)
        self.stack.addWidget(self.view_tools)
        self.stack.addWidget(self.view_logs)
        self.stack.addWidget(self.view_settings)

        body_layout.addWidget(self.stack)
        main_vbox.addLayout(body_layout)

        # Select Core Dashboard by default
        self.btn_dash.setChecked(True)

    def _create_nav_button(self, label: str, index: int) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("jarvisNavButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(index))
        self.nav_group.addButton(btn)
        return btn

    def _start_telemetry_loop(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sync_telemetry)
        self.timer.start(1500)
        self._sync_telemetry()

    def _sync_telemetry(self):
        status = self.bridge.get_current_status()
        self.top_bar.update_telemetry(status)
        self.view_dash.update_telemetry(status)
        self.view_telemetry.refresh_metrics()


def launch_jarvis_app():
    """Application entry point for JARVIS Control Center."""
    app = QApplication(sys.argv)
    window = JarvisControlCenterWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_jarvis_app()
