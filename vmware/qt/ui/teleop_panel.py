"""Dead-man teleop panel: five buttons, hold-to-move."""

import logging

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class TeleopPanel(QWidget):
    velocity_requested = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, linear_speed=0.10, angular_speed=0.25, repeat_hz=10, parent=None):
        super(TeleopPanel, self).__init__(parent)
        self._linear = float(linear_speed)
        self._angular = float(angular_speed)
        self._active_velocity = (0.0, 0.0, 0.0)
        self._controls_enabled = True
        self._repeat_timer = QTimer(self)
        interval_ms = max(50, int(1000.0 / max(1, repeat_hz)))
        self._repeat_timer.setInterval(interval_ms)
        self._repeat_timer.timeout.connect(self._repeat_active_velocity)
        self._buttons = []
        self._build_ui()

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    def set_speeds(self, linear, angular):
        self._linear = float(linear)
        self._angular = float(angular)

    def set_controls_enabled(self, enabled, reason=""):
        self._controls_enabled = bool(enabled)
        for btn in self._buttons:
            btn.setEnabled(self._controls_enabled)
        if not self._controls_enabled:
            self._stop_motion("disabled")
            if reason:
                self._hint_label.setText(reason)
        else:
            self._hint_label.setText(self._default_hint())

    def stop(self):
        if self._motion_active():
            self._stop_motion("stop_call")

    def _default_hint(self):
        return (
            "按住运动、松开停止（约 10Hz）。左/右为原地转向，非横移。"
            "非硬件急停；需小车 radar2d-start / full-start。"
        )

    def _motion_active(self):
        return self._repeat_timer.isActive()

    def _build_ui(self):
        root = QVBoxLayout(self)
        group = QGroupBox("基础遥控 (/cmd_vel)")
        grid = QGridLayout()
        grid.setSpacing(6)

        actions = [
            (0, 1, "前进", lambda: self._emit_vel(self._linear, 0.0, 0.0), False),
            (2, 1, "后退", lambda: self._emit_vel(-self._linear, 0.0, 0.0), False),
            (1, 0, "左转", lambda: self._emit_vel(0.0, 0.0, self._angular), False),
            (1, 2, "右转", lambda: self._emit_vel(0.0, 0.0, -self._angular), False),
            (1, 1, "停止", self._on_stop_button, True),
        ]
        for row, col, text, handler, is_stop in actions:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            btn.setAutoRepeat(False)
            self._buttons.append(btn)
            if is_stop:
                btn.setStyleSheet(
                    "QPushButton { background: #e53935; color: white; font-weight: 600; }"
                )
                btn.clicked.connect(handler)
            else:
                btn.pressed.connect(handler)
                btn.released.connect(self._on_button_released)
            grid.addWidget(btn, row, col)

        self._hint_label = QLabel(self._default_hint())
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("color: #666; font-size: 11px;")

        group_layout = QVBoxLayout()
        group_layout.addLayout(grid)
        group_layout.addWidget(self._hint_label)
        group.setLayout(group_layout)
        root.addWidget(group)

    def _emit_vel(self, lx, ly, az):
        if not self._controls_enabled:
            return
        self._active_velocity = (lx, ly, az)
        logger.info("teleop emit lx=%.3f ly=%.3f az=%.3f", lx, ly, az)
        self.velocity_requested.emit(lx, ly, az)
        if not self._repeat_timer.isActive():
            self._repeat_timer.start()

    def _repeat_active_velocity(self):
        lx, ly, az = self._active_velocity
        self.velocity_requested.emit(lx, ly, az)

    def _on_stop_button(self):
        self._stop_motion("button")

    def _stop_motion(self, reason):
        had_motion = self._motion_active()
        self._repeat_timer.stop()
        self._active_velocity = (0.0, 0.0, 0.0)
        if had_motion:
            logger.info("teleop stop reason=%s", reason)
            self.stop_requested.emit()

    def _on_button_released(self):
        if not self._motion_active():
            return
        self._stop_motion("button_release")

    def hideEvent(self, event):
        if self._motion_active():
            self._stop_motion("hide")
        super(TeleopPanel, self).hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowDeactivate and self._motion_active():
            self._stop_motion("window_deactivate")
        super(TeleopPanel, self).changeEvent(event)

    def _on_app_state_changed(self, state):
        if state == Qt.ApplicationActive:
            return
        if self._motion_active():
            self._stop_motion("application_inactive")
