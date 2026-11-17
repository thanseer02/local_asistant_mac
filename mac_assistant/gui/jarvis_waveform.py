"""Audio voice waveform visualizer widget for JARVIS Live Assistant."""

import math
import random
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class JarvisVoiceWaveform(QWidget):
    """Futuristic multi-bar animated voice equalizer / waveform."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.setMaximumHeight(80)
        self.bars = 36
        self.amplitudes = [0.1] * self.bars
        self.is_active = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_wave)
        self.timer.start(50)

    def set_active(self, active: bool):
        self.is_active = active
        self.update()

    def _update_wave(self):
        if not self.is_active:
            self.amplitudes = [0.05] * self.bars
        else:
            for i in range(self.bars):
                # Harmonic undulating wave simulation
                val = 0.2 + 0.7 * (math.sin(time.time() * 5 + i * 0.4) ** 2) * random.uniform(0.6, 1.0)
                self.amplitudes[i] = max(0.08, min(1.0, val))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        bar_width = (w - (self.bars * 4)) / self.bars
        mid_y = h / 2.0

        for i, amp in enumerate(self.amplitudes):
            x = i * (bar_width + 4) + 2
            bar_h = (h - 10) * amp
            top_y = mid_y - (bar_h / 2.0)

            # Cyan to Electric Blue gradient
            col = QColor(0, int(180 + 75 * amp), 255, 230)
            painter.setBrush(QBrush(col))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, top_y, bar_width, bar_h, 2, 2)


import time
