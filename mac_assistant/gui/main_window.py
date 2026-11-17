"""Main application window for Friday/Jarvis Control Center."""

import sys
from typing import Optional
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget
)

from mac_assistant.gui.bridge_service import AssistantBridgeService
from mac_assistant.gui.styles import DARK_THEME, LIGHT_THEME
from mac_assistant.gui.views import (
    ConversationHistoryView, DashboardView, PersonalityManagerView,
    SystemLogsView, ToolRegistryView
)


class ControlCenterMainWindow(QMainWindow):
    """
    macOS-styled Desktop GUI for Friday/Jarvis:
    - Sidebar navigation (Dashboard, History, Personalities, Tools, Logs).
    - Dark & Light mode toggle.
    - Live WebSocket/polling refresh for CPU, RAM, and background daemon status.
    - Safe actions and confirmation dialogs.
    """

    def __init__(self, bridge: Optional[AssistantBridgeService] = None):
        super().__init__()
        self.bridge = bridge or AssistantBridgeService()
        self.is_dark_theme = True

        self.setWindowTitle("Friday / Jarvis Control Center")
        self.resize(1050, 700)
        self.setMinimumSize(850, 550)

        self._init_ui()
        self._apply_theme()
        self._start_status_timer()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        root_layout = QHBoxLayout(main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 16)
        sb_layout.setSpacing(4)

        header = QLabel("🤖 Assistant", objectName="sidebarHeader")
        sb_layout.addWidget(header)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_dashboard = self._create_nav_button("📊  Dashboard", 0)
        self.btn_history = self._create_nav_button("💬  Conversation History", 1)
        self.btn_personality = self._create_nav_button("🎭  Personality & Voice", 2)
        self.btn_tools = self._create_nav_button("🛠️  Tool Registry", 3)
        self.btn_logs = self._create_nav_button("📜  System Logs", 4)

        sb_layout.addWidget(self.btn_dashboard)
        sb_layout.addWidget(self.btn_history)
        sb_layout.addWidget(self.btn_personality)
        sb_layout.addWidget(self.btn_tools)
        sb_layout.addWidget(self.btn_logs)
        sb_layout.addStretch()

        # Theme toggle button
        self.theme_btn = QPushButton("☀️  Light Mode")
        self.theme_btn.setObjectName("navButton")
        self.theme_btn.clicked.connect(self._toggle_theme)
        sb_layout.addWidget(self.theme_btn)

        root_layout.addWidget(self.sidebar)

        # 2. Main Content Stack
        self.stack = QStackedWidget()
        self.view_dashboard = DashboardView(self.bridge)
        self.view_history = ConversationHistoryView(self.bridge)
        self.view_personality = PersonalityManagerView(self.bridge)
        self.view_tools = ToolRegistryView(self.bridge)
        self.view_logs = SystemLogsView(self.bridge)

        self.stack.addWidget(self.view_dashboard)
        self.stack.addWidget(self.view_history)
        self.stack.addWidget(self.view_personality)
        self.stack.addWidget(self.view_tools)
        self.stack.addWidget(self.view_logs)

        root_layout.addWidget(self.stack)

        # Default select Dashboard
        self.btn_dashboard.setChecked(True)

    def _create_nav_button(self, text: str, index: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(index))
        self.nav_group.addButton(btn)
        return btn

    def _toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        if self.is_dark_theme:
            self.theme_btn.setText("☀️  Light Mode")
        else:
            self.theme_btn.setText("🌙  Dark Mode")
        self._apply_theme()

    def _apply_theme(self):
        stylesheet = DARK_THEME if self.is_dark_theme else LIGHT_THEME
        self.setStyleSheet(stylesheet)

    def _start_status_timer(self):
        """Polls bridge status every 2 seconds to update dashboard smoothly."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_live_status)
        self.timer.start(2000)
        self._refresh_live_status()

    def _refresh_live_status(self):
        status = self.bridge.get_current_status()
        self.view_dashboard.update_status(status)


def launch_gui():
    """Application launcher entry point."""
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = ControlCenterMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
