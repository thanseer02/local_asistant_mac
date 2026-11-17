"""Native macOS Dark and Light Theme Stylesheets for PySide6 Control Center."""

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* Sidebar navigation */
#sidebar {
    background-color: #161616;
    border-right: 1px solid #2d2d2d;
    min-width: 210px;
    max-width: 210px;
}

#sidebarHeader {
    padding: 16px;
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
    border-bottom: 1px solid #262626;
}

#navButton {
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #a0a0a0;
    background-color: transparent;
    border: none;
    margin: 2px 8px;
}

#navButton:hover {
    background-color: #262626;
    color: #ffffff;
}

#navButton:checked {
    background-color: #007aff;
    color: #ffffff;
    font-weight: 600;
}

/* Cards & Content containers */
#card {
    background-color: #252525;
    border: 1px solid #333333;
    border-radius: 12px;
    padding: 16px;
}

#cardTitle {
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 8px;
}

/* Status Badges */
#badgeOnline {
    background-color: rgba(52, 199, 89, 0.2);
    color: #34c759;
    border: 1px solid #34c759;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}

#badgeOffline {
    background-color: rgba(255, 69, 58, 0.2);
    color: #ff453a;
    border: 1px solid #ff453a;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}

/* Buttons */
QPushButton {
    background-color: #3a3a3c;
    color: #ffffff;
    border: 1px solid #48484a;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #48484a;
}

QPushButton:pressed {
    background-color: #2c2c2e;
}

#primaryButton {
    background-color: #007aff;
    border: 1px solid #0063d1;
    color: #ffffff;
    font-weight: 600;
}

#primaryButton:hover {
    background-color: #1a88ff;
}

#dangerButton {
    background-color: #ff453a;
    border: 1px solid #d9382e;
    color: #ffffff;
    font-weight: 600;
}

#dangerButton:hover {
    background-color: #ff5b52;
}

/* Inputs & Form Controls */
QLineEdit, QComboBox, QSpinBox, QSlider {
    background-color: #2c2c2e;
    border: 1px solid #3a3a3c;
    border-radius: 6px;
    color: #ffffff;
    padding: 6px 10px;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #007aff;
}

/* Tables & Lists */
QTableWidget, QListWidget, QTextEdit {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 8px;
    gridline-color: #2d2d2d;
    color: #e0e0e0;
}

QHeaderView::section {
    background-color: #252525;
    border: none;
    border-bottom: 1px solid #333333;
    padding: 6px;
    font-weight: 600;
    color: #a0a0a0;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
}

QScrollBar::handle:vertical {
    background: #48484a;
    border-radius: 4px;
    min-height: 20px;
}
"""

LIGHT_THEME = """
QMainWindow, QWidget {
    background-color: #f5f5f7;
    color: #1d1d1f;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

#sidebar {
    background-color: #e5e5ea;
    border-right: 1px solid #d1d1d6;
    min-width: 210px;
    max-width: 210px;
}

#sidebarHeader {
    padding: 16px;
    font-size: 16px;
    font-weight: bold;
    color: #1d1d1f;
    border-bottom: 1px solid #d1d1d6;
}

#navButton {
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #48484a;
    background-color: transparent;
    border: none;
    margin: 2px 8px;
}

#navButton:hover {
    background-color: #d1d1d6;
    color: #000000;
}

#navButton:checked {
    background-color: #007aff;
    color: #ffffff;
    font-weight: 600;
}

#card {
    background-color: #ffffff;
    border: 1px solid #e5e5ea;
    border-radius: 12px;
    padding: 16px;
}

#cardTitle {
    font-size: 14px;
    font-weight: 600;
    color: #1d1d1f;
    margin-bottom: 8px;
}

#badgeOnline {
    background-color: rgba(52, 199, 89, 0.15);
    color: #248a3d;
    border: 1px solid #34c759;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}

#badgeOffline {
    background-color: rgba(255, 59, 48, 0.15);
    color: #d70015;
    border: 1px solid #ff3b30;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}

QPushButton {
    background-color: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #f2f2f7;
}

#primaryButton {
    background-color: #007aff;
    border: 1px solid #0063d1;
    color: #ffffff;
    font-weight: 600;
}

#primaryButton:hover {
    background-color: #0056b3;
}

#dangerButton {
    background-color: #ff3b30;
    border: 1px solid #d70015;
    color: #ffffff;
    font-weight: 600;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #ffffff;
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    color: #1d1d1f;
    padding: 6px 10px;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #007aff;
}

QTableWidget, QListWidget, QTextEdit {
    background-color: #ffffff;
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    gridline-color: #e5e5ea;
    color: #1d1d1f;
}

QHeaderView::section {
    background-color: #f2f2f7;
    border: none;
    border-bottom: 1px solid #d1d1d6;
    padding: 6px;
    font-weight: 600;
    color: #636366;
}
"""
