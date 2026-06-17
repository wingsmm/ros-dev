from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QGroupBox, QPushButton, QVBoxLayout, QWidget


class ManualControlStrip(QWidget):
    """Compact button-based teleop; emits velocity signals only (no ROS)."""

    velocity_requested = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._linear = 0.10
        self._angular = 0.20
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        group = QGroupBox("手动遥控（占位，暂不发送速度）")
        grid = QGridLayout(group)
        grid.setSpacing(6)

        defs = [
            (0, 1, "前进", lambda: self._emit_vel(self._linear, 0.0, 0.0)),
            (2, 1, "后退", lambda: self._emit_vel(-self._linear, 0.0, 0.0)),
            (1, 0, "左移", lambda: self._emit_vel(0.0, self._linear, 0.0)),
            (1, 2, "右移", lambda: self._emit_vel(0.0, -self._linear, 0.0)),
            (1, 1, "停止", self._emit_stop),
            (0, 0, "左转", lambda: self._emit_vel(0.0, 0.0, self._angular)),
            (0, 2, "右转", lambda: self._emit_vel(0.0, 0.0, -self._angular)),
        ]
        for row, col, text, handler in defs:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            if text == "停止":
                btn.setStyleSheet(
                    "QPushButton { background: #e53935; color: white; font-weight: 600; }"
                )
            btn.clicked.connect(handler)
            grid.addWidget(btn, row, col)

        root.addWidget(group)

    def _emit_vel(self, lx: float, ly: float, az: float) -> None:
        self.velocity_requested.emit(lx, ly, az)

    def _emit_stop(self) -> None:
        self.stop_requested.emit()
        self.velocity_requested.emit(0.0, 0.0, 0.0)

    def stop(self) -> None:
        self._emit_stop()
