"""Futuristic HUD Dashboard with central animated Arc Reactor Core."""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget
)

from mac_assistant.gui.bridge_service import AssistantBridgeService, SystemStatus
from mac_assistant.gui.jarvis_core_widget import JarvisArcReactorCore


class JarvisDashboardView(QWidget):
    """Futuristic Iron Man HUD Dashboard."""

    def __init__(self, bridge: AssistantBridgeService, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(16)

        # 1. Central Core HUD Panel
        core_panel = QFrame()
        core_panel.setObjectName("hudPanel")
        cp_layout = QVBoxLayout(core_panel)
        cp_layout.setAlignment(Qt.AlignCenter)

        self.core_widget = JarvisArcReactorCore()
        cp_layout.addWidget(self.core_widget)

        self.core_title = QLabel("J.A.R.V.I.S. NEURAL CORE ONLINE")
        self.core_title.setObjectName("coreStatusLabel")
        self.core_title.setAlignment(Qt.AlignCenter)
        cp_layout.addWidget(self.core_title)

        self.core_subtext = QLabel("Awaiting voice invocation or command telemetry...")
        self.core_subtext.setStyleSheet("color: #79a8cc; font-size: 12px;")
        self.core_subtext.setAlignment(Qt.AlignCenter)
        cp_layout.addWidget(self.core_subtext)

        layout.addWidget(core_panel)

        # 2. Split Cards (Quick Command Terminal & Telemetry)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(14)

        # Command Dispatch
        cmd_card = QFrame()
        cmd_card.setObjectName("hudPanel")
        cc_lay = QVBoxLayout(cmd_card)
        cc_lay.addWidget(QLabel("DIRECT COMMAND TERMINAL", objectName="hudPanelTitle"))

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Enter instruction (e.g. 'check git status', 'time', 'flutter doctor')...")
        self.cmd_input.returnPressed.connect(self._run_quick_command)
        cc_lay.addWidget(self.cmd_input)

        b_row = QHBoxLayout()
        self.run_btn = QPushButton("EXECUTE COMMAND")
        self.run_btn.setObjectName("cyanAccentButton")
        self.run_btn.clicked.connect(self._run_quick_command)
        b_row.addWidget(self.run_btn)

        self.switch_persona_btn = QPushButton("SWITCH TO FRIDAY")
        self.switch_persona_btn.clicked.connect(self._toggle_persona)
        b_row.addWidget(self.switch_persona_btn)
        cc_lay.addLayout(b_row)

        self.cmd_result = QLabel("Console output ready.")
        self.cmd_result.setStyleSheet("color: #00ffaa; font-family: Menlo, monospace; font-size: 12px;")
        self.cmd_result.setWordWrap(True)
        cc_lay.addWidget(self.cmd_result)

        split_layout.addWidget(cmd_card)

        # Live Activity Feed
        feed_card = QFrame()
        feed_card.setObjectName("hudPanel")
        fc_lay = QVBoxLayout(feed_card)
        fc_lay.addWidget(QLabel("RECENT ACTIVITY TELEMETRY", objectName="hudPanelTitle"))
        self.activity_box = QTextEdit()
        self.activity_box.setReadOnly(True)
        self.activity_box.setStyleSheet("font-family: Menlo, monospace; font-size: 11px; background-color: #040c17;")
        fc_lay.addWidget(self.activity_box)

        split_layout.addWidget(feed_card)
        layout.addLayout(split_layout)

    def update_telemetry(self, status: SystemStatus):
        # Update Core State
        if status.online:
            self.core_title.setText(f"{status.active_persona.upper()} NEURAL INTERFACE ONLINE")
            self.core_widget.set_state_mode("STANDBY")
        else:
            self.core_title.setText("CORE SYSTEM OFFLINE")
            self.core_widget.set_state_mode("OFFLINE")

        self.core_subtext.setText(
            f"Active Voice: {status.voice} ({status.speech_rate} WPM) | Host PID: {status.active_pid or '--'} | "
            f"CPU: {status.cpu_percent:.1f}% | RAM: {status.ram_percent:.1f}%"
        )

        if status.active_persona.lower() == "friday":
            self.switch_persona_btn.setText("SWITCH TO JARVIS")
        else:
            self.switch_persona_btn.setText("SWITCH TO FRIDAY")

        logs = self.bridge.get_logs(max_lines=15)
        self.activity_box.setPlainText("\n".join(logs))
        self.activity_box.verticalScrollBar().setValue(self.activity_box.verticalScrollBar().maximum())

    def _run_quick_command(self):
        cmd = self.cmd_input.text().strip()
        if not cmd:
            return
        self.cmd_input.clear()
        self.core_widget.set_state_mode("THINKING")

        from mac_assistant.conversation_router import ConversationRouter
        router = ConversationRouter()
        status = self.bridge.get_current_status()
        intent, ok, resp = router.route(cmd, persona=status.active_persona)

        self.cmd_result.setText(f"[{intent.upper()}]: {resp}")
        self.core_widget.set_state_mode("SPEAKING")

    def _toggle_persona(self):
        status = self.bridge.get_current_status()
        new_target = "friday" if status.active_persona.lower() == "jarvis" else "jarvis"
        self.bridge.switch_active_persona(new_target)
        self.bridge.restart_assistant_service()
