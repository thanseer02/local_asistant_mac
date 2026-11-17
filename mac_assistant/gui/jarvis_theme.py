"""Futuristic Iron Man HUD and Glassmorphism Stylesheet for JARVIS Control Center."""

JARVIS_FUTURISTIC_THEME = """
QMainWindow, QWidget {
    background-color: #050b14;
    color: #e2f1ff;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

/* Glassmorphism Sidebar */
#jarvisSidebar {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #081220, stop:1 #040912);
    border-right: 1px solid rgba(0, 210, 255, 0.18);
    min-width: 230px;
    max-width: 230px;
}

#jarvisLogoHeader {
    padding: 20px 16px 14px 16px;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 2.5px;
    color: #00e5ff;
    border-bottom: 1px solid rgba(0, 229, 255, 0.15);
}

#jarvisNavButton {
    text-align: left;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #7da5c9;
    background-color: transparent;
    border: 1px solid transparent;
    margin: 3px 10px;
}

#jarvisNavButton:hover {
    background-color: rgba(0, 229, 255, 0.08);
    color: #00e5ff;
    border: 1px solid rgba(0, 229, 255, 0.25);
}

#jarvisNavButton:checked {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(0, 150, 255, 0.35), stop:1 rgba(0, 229, 255, 0.15));
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #00e5ff;
}

/* Top Futuristic Status Bar */
#jarvisTopBar {
    background-color: #060e1a;
    border-bottom: 1px solid rgba(0, 229, 255, 0.2);
    padding: 8px 20px;
    min-height: 44px;
    max-height: 44px;
}

#topBarStatusOnline {
    background-color: rgba(0, 255, 170, 0.15);
    color: #00ffaa;
    border: 1px solid #00ffaa;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 1px;
}

#topBarMetrics {
    color: #8bbcd8;
    font-size: 12px;
    font-weight: 500;
}

/* Futuristic HUD Glass Panels */
#hudPanel {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(8, 24, 44, 0.7), stop:1 rgba(4, 12, 22, 0.8));
    border: 1px solid rgba(0, 229, 255, 0.22);
    border-radius: 12px;
    padding: 18px;
}

#hudPanelTitle {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #00e5ff;
    margin-bottom: 6px;
}

/* Arc Reactor Core Glow Label */
#coreStatusLabel {
    color: #00e5ff;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 2px;
}

/* Buttons */
QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f2742, stop:1 #091728);
    color: #cbe5ff;
    border: 1px solid rgba(0, 229, 255, 0.3);
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QPushButton:hover {
    background-color: rgba(0, 229, 255, 0.18);
    border: 1px solid #00e5ff;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #040e1a;
}

#cyanAccentButton {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0088cc, stop:1 #00e5ff);
    color: #02070f;
    border: 1px solid #00f0ff;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 700;
    letter-spacing: 0.8px;
}

#cyanAccentButton:hover {
    background-color: #00ffff;
    color: #000000;
}

/* Input Fields */
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: #081626;
    border: 1px solid rgba(0, 229, 255, 0.25);
    border-radius: 8px;
    color: #e2f1ff;
    padding: 8px 12px;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #00e5ff;
    background-color: #0c2038;
}

/* Progress Bars */
QProgressBar {
    background-color: #081729;
    border: 1px solid rgba(0, 229, 255, 0.2);
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    font-size: 11px;
    height: 14px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0077b6, stop:1 #00e5ff);
    border-radius: 5px;
}

/* Table Widget */
QTableWidget {
    background-color: #06111f;
    border: 1px solid rgba(0, 229, 255, 0.18);
    border-radius: 8px;
    gridline-color: rgba(0, 229, 255, 0.1);
    color: #d8eeff;
}

QHeaderView::section {
    background-color: #0a1c30;
    border: none;
    border-bottom: 1px solid rgba(0, 229, 255, 0.3);
    padding: 8px;
    font-weight: 700;
    color: #00e5ff;
    letter-spacing: 0.8px;
}
"""
