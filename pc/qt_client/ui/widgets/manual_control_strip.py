from __future__ import annotations

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QGroupBox, QPushButton, QVBoxLayout, QWidget


class ManualControlStrip(QWidget):
    """Compact dead-man teleop; emits velocity signals only while held."""

    velocity_requested = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._linear = 0.10
        self._angular = 0.20
        self._active_velocity = (0.0, 0.0, 0.0)
        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(100)
        self._repeat_timer.timeout.connect(self._repeat_active_velocity)
        self._build_ui()

    def set_speeds(self, linear: float, angular: float) -> None:
        self._linear = float(linear)
        self._angular = float(angular)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        group = QGroupBox("手动遥控（按住才运动，松开即停止）")
        grid = QGridLayout(group)
        grid.setSpacing(6)

        actions = [
            (0, 1, "前进", lambda: self._emit_vel(self._linear, 0.0, 0.0), False),
            (2, 1, "后退", lambda: self._emit_vel(-self._linear, 0.0, 0.0), False),
            (1, 0, "左移", lambda: self._emit_vel(0.0, self._linear, 0.0), False),
            (1, 2, "右移", lambda: self._emit_vel(0.0, -self._linear, 0.0), False),
            (1, 1, "停止", self._emit_stop, True),
            (0, 0, "左转", lambda: self._emit_vel(0.0, 0.0, self._angular), False),
            (0, 2, "右转", lambda: self._emit_vel(0.0, 0.0, -self._angular), False),
        ]
        for row, col, text, handler, is_stop in actions:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            btn.setAutoRepeat(False)
            if is_stop:
                btn.setStyleSheet(
                    "QPushButton { background: #e53935; color: white; font-weight: 600; }"
                )
                btn.clicked.connect(handler)
            else:
                # Dead-man control: motion is active only while the button is held.
                btn.pressed.connect(handler)
                btn.released.connect(self._emit_stop)
            grid.addWidget(btn, row, col)

        root.addWidget(group)

    def _emit_vel(self, lx: float, ly: float, az: float) -> None:
        self._active_velocity = (lx, ly, az)
        self.velocity_requested.emit(lx, ly, az)
        if not self._repeat_timer.isActive():
            self._repeat_timer.start()

    def _repeat_active_velocity(self) -> None:
        lx, ly, az = self._active_velocity
        self.velocity_requested.emit(lx, ly, az)

    def _emit_stop(self) -> None:
        self._repeat_timer.stop()
        self._active_velocity = (0.0, 0.0, 0.0)
        self.stop_requested.emit()

    def stop(self) -> None:
        self._emit_stop()
