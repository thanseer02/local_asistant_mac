"""Views and tab widgets for Friday/Jarvis Control Center."""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget
)

from mac_assistant.gui.bridge_service import AssistantBridgeService, SystemStatus


class DashboardView(QWidget):
    """Overview dashboard showing online status, personality, model, CPU/RAM, and actions."""

    def __init__(self, bridge: AssistantBridgeService, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        header = QLabel("System Dashboard")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(header)

        # Metrics Card Row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        # 1. Status Card
        self.status_card = QFrame()
        self.status_card.setObjectName("card")
        sc_layout = QVBoxLayout(self.status_card)
        sc_layout.addWidget(QLabel("Assistant Status", objectName="cardTitle"))
        self.status_badge = QLabel("INITIALIZING")
        self.status_badge.setObjectName("badgeOffline")
        self.status_badge.setAlignment(Qt.AlignCenter)
        sc_layout.addWidget(self.status_badge)
        self.pid_label = QLabel("PID: --")
        sc_layout.addWidget(self.pid_label)
        metrics_layout.addWidget(self.status_card)

        # 2. Active Persona Card
        self.persona_card = QFrame()
        self.persona_card.setObjectName("card")
        pc_layout = QVBoxLayout(self.persona_card)
        pc_layout.addWidget(QLabel("Active Persona", objectName="cardTitle"))
        self.persona_label = QLabel("Friday (Moira)")
        self.persona_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #007aff;")
        pc_layout.addWidget(self.persona_label)
        self.voice_details_label = QLabel("Voice Rate: 172 wpm")
        pc_layout.addWidget(self.voice_details_label)
        metrics_layout.addWidget(self.persona_card)

        # 3. AI Engine Card
        self.ai_card = QFrame()
        self.ai_card.setObjectName("card")
        ac_layout = QVBoxLayout(self.ai_card)
        ac_layout.addWidget(QLabel("Local AI Model", objectName="cardTitle"))
        self.model_label = QLabel("llama3.2:1b")
        self.model_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #34c759;")
        ac_layout.addWidget(self.model_label)
        ac_layout.addWidget(QLabel("100% Offline Ollama Service"))
        metrics_layout.addWidget(self.ai_card)

        # 4. Resource Usage Card
        self.res_card = QFrame()
        self.res_card.setObjectName("card")
        rc_layout = QVBoxLayout(self.res_card)
        rc_layout.addWidget(QLabel("Resource Usage", objectName="cardTitle"))
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setFormat("CPU: %p%")
        rc_layout.addWidget(self.cpu_bar)
        self.ram_bar = QProgressBar()
        self.ram_bar.setFormat("RAM: %p%")
        rc_layout.addWidget(self.ram_bar)
        metrics_layout.addWidget(self.res_card)

        layout.addLayout(metrics_layout)

        # Quick Controls Card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        cc_layout = QVBoxLayout(ctrl_card)
        cc_layout.addWidget(QLabel("Quick Controls", objectName="cardTitle"))

        btn_row = QHBoxLayout()
        self.switch_persona_btn = QPushButton("Switch to Jarvis")
        self.switch_persona_btn.setObjectName("primaryButton")
        self.switch_persona_btn.clicked.connect(self._toggle_persona)
        btn_row.addWidget(self.switch_persona_btn)

        self.restart_btn = QPushButton("Restart Assistant Daemon")
        self.restart_btn.clicked.connect(self._restart_daemon)
        btn_row.addWidget(self.restart_btn)

        self.clear_hist_btn = QPushButton("Clear Session Memory")
        self.clear_hist_btn.clicked.connect(self._clear_memory)
        btn_row.addWidget(self.clear_hist_btn)

        cc_layout.addLayout(btn_row)
        layout.addWidget(ctrl_card)

        # Recent Log Output Box
        log_card = QFrame()
        log_card.setObjectName("card")
        lc_layout = QVBoxLayout(log_card)
        lc_layout.addWidget(QLabel("Live Assistant Activity Log", objectName="cardTitle"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Menlo, monospace; font-size: 11px;")
        lc_layout.addWidget(self.log_text)
        layout.addWidget(log_card)

    def update_status(self, status: SystemStatus):
        if status.online:
            self.status_badge.setText(f"ONLINE ({status.state})")
            self.status_badge.setObjectName("badgeOnline")
        else:
            self.status_badge.setText("OFFLINE")
            self.status_badge.setObjectName("badgeOffline")
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

        self.pid_label.setText(f"PID: {status.active_pid or '--'} | Refreshed: {status.timestamp}")
        p_name = status.active_persona.capitalize()
        self.persona_label.setText(f"{p_name} ({status.voice})")
        self.voice_details_label.setText(f"Speech Rate: {status.speech_rate} wpm")

        # Toggle button text
        if status.active_persona.lower() == "friday":
            self.switch_persona_btn.setText("Switch to Jarvis")
        else:
            self.switch_persona_btn.setText("Switch to Friday")

        self.cpu_bar.setValue(int(status.cpu_percent))
        self.ram_bar.setValue(int(status.ram_percent))

        # Recent activities
        recent = self.bridge.get_logs(max_lines=25)
        self.log_text.setPlainText("\n".join(recent))
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _toggle_persona(self):
        status = self.bridge.get_current_status()
        new_target = "jarvis" if status.active_persona.lower() == "friday" else "friday"
        self.bridge.switch_active_persona(new_target)
        self.bridge.restart_assistant_service()

    def _restart_daemon(self):
        ok, msg = self.bridge.restart_assistant_service()
        QMessageBox.information(self, "Restart Result", msg if ok else f"Error: {msg}")

    def _clear_memory(self):
        reply = QMessageBox.question(
            self, "Confirm Clear",
            "Are you sure you want to wipe conversation history from SQLite memory?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.bridge.clear_conversation_history()
            QMessageBox.information(self, "Memory Cleared", "Conversation memory has been wiped.")


class ConversationHistoryView(QWidget):
    """Browses, filters, searches, and exports multi-turn conversation history."""

    def __init__(self, bridge: AssistantBridgeService, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QLabel("Conversation History")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(header)

        # Filter bar
        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search conversation keywords...")
        self.search_input.textChanged.connect(self.refresh_history)
        filter_row.addWidget(self.search_input)

        self.persona_filter = QComboBox()
        self.persona_filter.addItems(["All Personas", "Friday", "Jarvis"])
        self.persona_filter.currentIndexChanged.connect(self.refresh_history)
        filter_row.addWidget(self.persona_filter)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_history)
        filter_row.addWidget(self.refresh_btn)

        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Timestamp", "Speaker", "Message Content"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Bottom row
        b_row = QHBoxLayout()
        self.export_btn = QPushButton("Export Transcript (.txt)")
        self.export_btn.clicked.connect(self._export_transcript)
        b_row.addWidget(self.export_btn)
        b_row.addStretch()
        layout.addLayout(b_row)

        self.refresh_history()

    def refresh_history(self):
        query = self.search_input.text()
        filter_p = self.persona_filter.currentText()
        p_arg = None if filter_p == "All Personas" else filter_p.lower()

        turns = self.bridge.get_conversation_history(persona_filter=p_arg, search_query=query, limit=100)
        self.table.setRowCount(len(turns))

        for row, turn in enumerate(turns):
            self.table.setItem(row, 0, QTableWidgetItem(str(turn["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(turn["timestamp"]))
            speaker = "You" if turn["role"] == "user" else "Assistant"
            self.table.setItem(row, 2, QTableWidgetItem(speaker))
            self.table.setItem(row, 3, QTableWidgetItem(turn["content"]))

    def _export_transcript(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Conversation History", "conversation_export.txt", "Text Files (*.txt)")
        if path:
            turns = self.bridge.get_conversation_history(limit=500)
            with open(path, "w", encoding="utf-8") as f:
                for t in turns:
                    f.write(f"[{t['timestamp']}] {t['role'].upper()}: {t['content']}\n\n")
            QMessageBox.information(self, "Export Complete", f"Saved {len(turns)} conversation turns to {path}.")


class PersonalityManagerView(QWidget):
    """Detailed side-by-side personality configuration for Friday and Jarvis."""

    def __init__(self, bridge: AssistantBridgeService, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Personality & Voice Settings")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(header)

        # Columns for Friday & Jarvis
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # --- Friday Card ---
        self.friday_card = QFrame()
        self.friday_card.setObjectName("card")
        f_layout = QVBoxLayout(self.friday_card)
        f_header = QLabel("Friday (Warm & Natural)")
        f_header.setStyleSheet("font-size: 16px; font-weight: 600; color: #ff9500;")
        f_layout.addWidget(f_header)

        f_form = QFormLayout()
        self.f_length = QComboBox()
        self.f_length.addItems(["concise", "detailed", "adaptive"])
        f_form.addRow("Response Length:", self.f_length)

        self.f_humor = QCheckBox("Lighthearted Humor & Banter")
        f_form.addRow("Humor:", self.f_humor)

        self.f_salutation = QCheckBox("Address User as 'Boss'")
        f_form.addRow("Salutation:", self.f_salutation)

        self.f_voice = QComboBox()
        self.f_voice.addItems(["Moira", "Samantha", "Karen", "Tessa"])
        f_form.addRow("macOS Voice:", self.f_voice)

        self.f_rate = QSpinBox()
        self.f_rate.setRange(120, 220)
        f_form.addRow("Speech Rate (WPM):", self.f_rate)

        f_layout.addLayout(f_form)

        f_save = QPushButton("Save Friday Configuration")
        f_save.setObjectName("primaryButton")
        f_save.clicked.connect(self._save_friday)
        f_layout.addWidget(f_save)
        cols.addWidget(self.friday_card)

        # --- Jarvis Card ---
        self.jarvis_card = QFrame()
        self.jarvis_card.setObjectName("card")
        j_layout = QVBoxLayout(self.jarvis_card)
        j_header = QLabel("Jarvis (Sophisticated & Executive)")
        j_header.setStyleSheet("font-size: 16px; font-weight: 600; color: #007aff;")
        j_layout.addWidget(j_header)

        j_form = QFormLayout()
        self.j_length = QComboBox()
        self.j_length.addItems(["concise", "detailed", "adaptive"])
        j_form.addRow("Response Length:", self.j_length)

        self.j_humor = QCheckBox("Subtle British Wit & Irony")
        j_form.addRow("Humor:", self.j_humor)

        self.j_salutation = QCheckBox("Address User as 'Sir'")
        j_form.addRow("Salutation:", self.j_salutation)

        self.j_voice = QComboBox()
        self.j_voice.addItems(["Daniel", "Rishi", "Ralph", "Fred"])
        j_form.addRow("macOS Voice:", self.j_voice)

        self.j_rate = QSpinBox()
        self.j_rate.setRange(120, 220)
        j_form.addRow("Speech Rate (WPM):", self.j_rate)

        j_layout.addLayout(j_form)

        j_save = QPushButton("Save Jarvis Configuration")
        j_save.setObjectName("primaryButton")
        j_save.clicked.connect(self._save_jarvis)
        j_layout.addWidget(j_save)
        cols.addWidget(self.jarvis_card)

        layout.addLayout(cols)
        layout.addStretch()

        self.load_settings()

    def load_settings(self):
        f_cfg = self.bridge.friday_mgr.config
        self.f_length.setCurrentText(f_cfg.response_length)
        self.f_humor.setChecked(f_cfg.humor)
        self.f_salutation.setChecked(f_cfg.use_salutation)
        self.f_voice.setCurrentText(f_cfg.voice)
        self.f_rate.setValue(f_cfg.speech_rate)

        j_cfg = self.bridge.jarvis_mgr.config
        self.j_length.setCurrentText(j_cfg.response_length)
        self.j_humor.setChecked(j_cfg.humor)
        self.j_salutation.setChecked(j_cfg.use_salutation)
        self.j_voice.setCurrentText(j_cfg.voice)
        self.j_rate.setValue(j_cfg.speech_rate)

    def _save_friday(self):
        updates = {
            "response_length": self.f_length.currentText(),
            "humor": self.f_humor.isChecked(),
            "use_salutation": self.f_salutation.isChecked(),
            "voice": self.f_voice.currentText(),
            "speech_rate": self.f_rate.value()
        }
        self.bridge.update_friday_settings(updates)
        QMessageBox.information(self, "Friday Settings", "Friday configuration updated and persisted.")

    def _save_jarvis(self):
        updates = {
            "response_length": self.j_length.currentText(),
            "humor": self.j_humor.isChecked(),
            "use_salutation": self.j_salutation.isChecked(),
            "voice": self.j_voice.currentText(),
            "speech_rate": self.j_rate.value()
        }
        self.bridge.update_jarvis_settings(updates)
        QMessageBox.information(self, "Jarvis Settings", "Jarvis configuration updated and persisted.")


class ToolRegistryView(QWidget):
    """Inspects dynamically registered Mac automation and developer tools with permission controls."""

    def __init__(self, bridge: AssistantBridgeService, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QLabel("Registered Tools & Permissions")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(header)

        desc = QLabel(
            "Central tool registry enforcing safe execution, strict allowlists, and explicit user confirmation."
        )
        desc.setStyleSheet("color: #8e8e93;")
        layout.addWidget(desc)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Category", "Permission Level", "Confirmation", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.refresh_tools()

    def refresh_tools(self):
        tools = self.bridge.get_registered_tools()
        self.table.setRowCount(len(tools))
        for row, tool in enumerate(tools):
            self.table.setItem(row, 0, QTableWidgetItem(tool["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(tool["category"]))
            self.table.setItem(row, 2, QTableWidgetItem(tool["permission_level"]))
            conf = "Required" if tool["requires_confirmation"] else "Auto-Approve"
            self.table.setItem(row, 3, QTableWidgetItem(conf))
            self.table.setItem(row, 4, QTableWidgetItem(tool["description"]))


class SystemLogsView(QWidget):
    """Live system logs viewer with search, filtering, and secret-redacted export."""

    def __init__(self, bridge: AssistantBridgeService, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QLabel("System & Audit Logs")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(header)

        # Filters
        row = QHBoxLayout()
        self.log_type = QComboBox()
        self.log_type.addItems(["Application Logs (/tmp/macassistant-error.log)", "Developer Audit Logs (data/developer_audit.log)"])
        self.log_type.currentIndexChanged.connect(self.refresh_logs)
        row.addWidget(self.log_type)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter text...")
        self.filter_input.textChanged.connect(self.refresh_logs)
        row.addWidget(self.filter_input)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_logs)
        row.addWidget(refresh_btn)
        layout.addLayout(row)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("font-family: Menlo, monospace; font-size: 11px;")
        layout.addWidget(self.log_area)

        # Export row
        b_row = QHBoxLayout()
        export_btn = QPushButton("Export Redacted Logs (.log)")
        export_btn.clicked.connect(self._export_logs)
        b_row.addWidget(export_btn)
        b_row.addStretch()
        layout.addLayout(b_row)

        self.refresh_logs()

    def refresh_logs(self):
        l_type = "audit" if self.log_type.currentIndex() == 1 else "app"
        lines = self.bridge.get_logs(max_lines=300, log_type=l_type)
        query = self.filter_input.text().lower()

        if query:
            lines = [l for l in lines if query in l.lower()]

        self.log_area.setPlainText("\n".join(lines))
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def _export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log File", "macassistant_logs.log", "Log Files (*.log)")
        if path:
            text = self.log_area.toPlainText()
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            QMessageBox.information(self, "Export Success", f"Logs exported to {path}.")
