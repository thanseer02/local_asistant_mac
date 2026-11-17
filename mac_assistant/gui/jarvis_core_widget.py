"""Animated circular holographic JARVIS core widget inspired by Iron Man's Arc Reactor."""

import math
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class JarvisArcReactorCore(QWidget):
    """
    Futuristic circular core featuring:
    - Multiple spinning concentric rings with HUD tick marks.
    - Pulsing glowing cyan/blue core.
    - Dynamic state animation: 'STANDBY', 'LISTENING', 'THINKING', 'SPEAKING'.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)

        self.angle_outer = 0.0
        self.angle_inner = 0.0
        self.pulse = 0.0
        self.pulse_dir = 1
        self.state_mode = "STANDBY"  # STANDBY, LISTENING, THINKING, SPEAKING

        # 60 FPS animation timer
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate_tick)
        self.anim_timer.start(16)

    def set_state_mode(self, mode: str):
        self.state_mode = mode.upper()
        self.update()

    def _animate_tick(self):
        # Rotation speeds
        speed = 2.0 if self.state_mode in ["THINKING", "LISTENING"] else 0.8
        self.angle_outer = (self.angle_outer + speed) % 360
        self.angle_inner = (self.angle_inner - (speed * 1.5)) % 360

        # Pulse breathing effect
        self.pulse += 0.02 * self.pulse_dir
        if self.pulse >= 1.0:
            self.pulse_dir = -1
        elif self.pulse <= 0.0:
            self.pulse_dir = 1

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        center = QPointF(w / 2.0, h / 2.0)
        radius = min(w, h) / 2.0 - 15

        if radius <= 10:
            return

        # 1. Background radial glow
        glow_grad = QRadialGradient(center, radius)
        glow_color = QColor(0, 229, 255, int(20 + 25 * self.pulse))
        if self.state_mode == "LISTENING":
            glow_color = QColor(0, 255, 170, int(35 + 30 * self.pulse))
        elif self.state_mode == "THINKING":
            glow_color = QColor(0, 150, 255, int(35 + 30 * self.pulse))
        elif self.state_mode == "SPEAKING":
            glow_color = QColor(0, 229, 255, int(45 + 35 * self.pulse))

        glow_grad.setColorAt(0.0, glow_color)
        glow_grad.setColorAt(0.8, QColor(0, 15, 35, 100))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

        # 2. Outer Ring with dashed arcs
        outer_pen = QPen(QColor(0, 229, 255, 180), 2)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.NoBrush)

        r_outer = radius * 0.95
        rect_outer = QRectF(center.x() - r_outer, center.y() - r_outer, r_outer * 2, r_outer * 2)

        # Draw 3 rotating arc segments
        for i in range(3):
            start_deg = self.angle_outer + (i * 120)
            painter.drawArc(rect_outer, int(start_deg * 16), int(75 * 16))

        # 3. Middle Ticks Ring (HUD Dial)
        r_mid = radius * 0.78
        tick_count = 36
        tick_pen = QPen(QColor(0, 229, 255, 140), 1.5)
        painter.setPen(tick_pen)

        for i in range(tick_count):
            deg = math.radians(self.angle_inner + (i * (360 / tick_count)))
            p1 = QPointF(center.x() + (r_mid - 4) * math.cos(deg), center.y() + (r_mid - 4) * math.sin(deg))
            p2 = QPointF(center.x() + (r_mid + 4) * math.cos(deg), center.y() + (r_mid + 4) * math.sin(deg))
            painter.drawLine(p1, p2)

        # 4. Inner Ring with segmented brackets
        r_inner = radius * 0.58
        rect_inner = QRectF(center.x() - r_inner, center.y() - r_inner, r_inner * 2, r_inner * 2)
        inner_pen = QPen(QColor(0, 255, 220, 220), 2.5)
        painter.setPen(inner_pen)
        painter.drawArc(rect_inner, int(-self.angle_outer * 16), int(120 * 16))
        painter.drawArc(rect_inner, int((-self.angle_outer + 180) * 16), int(120 * 16))

        # 5. Core Center Glowing Orb
        r_core = radius * 0.38 * (1.0 + 0.08 * self.pulse)
        core_grad = QRadialGradient(center, r_core)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        core_grad.setColorAt(0.4, QColor(0, 229, 255, 210))
        core_grad.setColorAt(1.0, QColor(0, 60, 140, 160))

        painter.setBrush(QBrush(core_grad))
        painter.setPen(QPen(QColor(0, 229, 255, 250), 2))
        painter.drawEllipse(center, r_core, r_core)

        # 6. Central State Label
        painter.setPen(QColor(10, 20, 35))
        font = QFont("SF Pro Display", 10, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        painter.drawText(
            QRectF(center.x() - r_core, center.y() - 10, r_core * 2, 20),
            Qt.AlignCenter,
            self.state_mode
        )
