"""Dead-man teleop panel: five buttons, hold-to-move; optional keyboard."""

import logging

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_STOP_KEYS = frozenset({Qt.Key_K, Qt.Key_Space})
_FORWARD_KEYS = frozenset({Qt.Key_W, Qt.Key_I, Qt.Key_Up})
_BACK_KEYS = frozenset({Qt.Key_S, Qt.Key_Down})
_TURN_LEFT_KEYS = frozenset({Qt.Key_A, Qt.Key_Q, Qt.Key_J, Qt.Key_Left})
_TURN_RIGHT_KEYS = frozenset({Qt.Key_D, Qt.Key_E, Qt.Key_L, Qt.Key_Right})
_MOTION_KEYS = _FORWARD_KEYS | _BACK_KEYS | _TURN_LEFT_KEYS | _TURN_RIGHT_KEYS

_TEXT_INPUT_TYPES = (
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
)


class TeleopPanel(QWidget):
    velocity_requested = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, linear_speed=0.10, angular_speed=0.25, repeat_hz=10, parent=None):
        super(TeleopPanel, self).__init__(parent)
        self._linear = float(linear_speed)
        self._angular = float(angular_speed)
        self._active_velocity = (0.0, 0.0, 0.0)
        self._controls_enabled = True
        self._keyboard_enabled = False
        self._pressed_keys = set()
        self._repeat_timer = QTimer(self)
        interval_ms = max(50, int(1000.0 / max(1, repeat_hz)))
        self._repeat_timer.setInterval(interval_ms)
        self._repeat_timer.timeout.connect(self._repeat_active_velocity)
        self._buttons = []
        self.setFocusPolicy(Qt.StrongFocus)
        self._build_ui()

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    def set_speeds(self, linear, angular):
        self._linear = float(linear)
        self._angular = float(angular)

    def set_keyboard_enabled(self, enabled):
        enabled = bool(enabled)
        if enabled == self._keyboard_enabled:
            return
        window = self.window()
        if self._keyboard_enabled and window is not None:
            window.removeEventFilter(self)
        self._keyboard_enabled = enabled
        if not enabled:
            self._pressed_keys.clear()
            if self._motion_active():
                self._stop_motion("keyboard_disabled")
        elif window is not None:
            window.installEventFilter(self)
        if hasattr(self, "_hint_label"):
            self._hint_label.setText(self._default_hint())

    def set_controls_enabled(self, enabled, reason=""):
        self._controls_enabled = bool(enabled)
        for btn in self._buttons:
            btn.setEnabled(self._controls_enabled)
        if not self._controls_enabled:
            self.set_keyboard_enabled(False)
            self._stop_motion("disabled")
            if reason:
                self._hint_label.setText(reason)
        else:
            self._hint_label.setText(self._default_hint())

    def stop(self):
        if self._motion_active() or self._pressed_keys:
            self._stop_motion("stop_call")

    def _default_hint(self):
        kb = ""
        if self._keyboard_enabled:
            kb = "键盘：W/↑ 前进，S/↓ 后退，A/Q/← 左转，D/E/→ 右转，K/Space 停止。"
        return (
            "按住运动、松开停止（约 10Hz）。左/右为原地转向，非横移。"
            "非硬件急停；需小车 radar2d-start / full-start。"
            + kb
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
        had_motion = self._motion_active() or bool(self._pressed_keys)
        self._repeat_timer.stop()
        self._active_velocity = (0.0, 0.0, 0.0)
        self._pressed_keys.clear()
        if had_motion:
            logger.info("teleop stop reason=%s", reason)
            self.stop_requested.emit()

    def _on_button_released(self):
        if self._pressed_keys and self._keyboard_enabled:
            self._apply_keyboard_motion()
            return
        if not self._motion_active():
            return
        self._stop_motion("button_release")

    @staticmethod
    def _focus_in_text_input():
        widget = QApplication.focusWidget()
        if widget is None:
            return False
        return isinstance(widget, _TEXT_INPUT_TYPES)

    def _should_handle_keyboard(self):
        return (
            self._keyboard_enabled
            and self._controls_enabled
            and self.isVisible()
            and not self._focus_in_text_input()
        )

    def _keyboard_velocity(self):
        lx = az = 0.0
        forward = bool(self._pressed_keys & _FORWARD_KEYS)
        back = bool(self._pressed_keys & _BACK_KEYS)
        if forward and not back:
            lx = self._linear
        elif back and not forward:
            lx = -self._linear

        turn_l = bool(self._pressed_keys & _TURN_LEFT_KEYS)
        turn_r = bool(self._pressed_keys & _TURN_RIGHT_KEYS)
        if turn_l and not turn_r:
            az = self._angular
        elif turn_r and not turn_l:
            az = -self._angular
        return lx, 0.0, az

    def _apply_keyboard_motion(self):
        if not self._pressed_keys:
            if self._motion_active():
                self._stop_motion("key_release")
            return
        lx, ly, az = self._keyboard_velocity()
        if lx == 0.0 and ly == 0.0 and az == 0.0:
            if self._motion_active():
                self._stop_motion("key_release")
            return
        self._emit_vel(lx, ly, az)

    def _handle_key_press(self, event):
        if not self._should_handle_keyboard():
            return False
        if event.isAutoRepeat():
            return True
        key = event.key()
        if key in _STOP_KEYS:
            self._stop_motion("key_stop")
            return True
        if key not in _MOTION_KEYS:
            return False
        if key not in self._pressed_keys:
            self._pressed_keys.add(key)
            self._apply_keyboard_motion()
        return True

    def _handle_key_release(self, event):
        if not self._keyboard_enabled:
            return False
        if event.isAutoRepeat():
            return True
        key = event.key()
        if key not in _MOTION_KEYS:
            return False
        if key in self._pressed_keys:
            self._pressed_keys.discard(key)
            self._apply_keyboard_motion()
        return True

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if self._handle_key_press(event):
                return True
        elif event.type() == QEvent.KeyRelease:
            if self._handle_key_release(event):
                return True
        elif event.type() == QEvent.WindowDeactivate:
            if self._motion_active() or self._pressed_keys:
                self._stop_motion("window_deactivate")
        return super(TeleopPanel, self).eventFilter(obj, event)

    def keyPressEvent(self, event):
        if self._handle_key_press(event):
            event.accept()
            return
        super(TeleopPanel, self).keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self._handle_key_release(event):
            event.accept()
            return
        super(TeleopPanel, self).keyReleaseEvent(event)

    def hideEvent(self, event):
        if self._motion_active() or self._pressed_keys:
            self._stop_motion("hide")
        super(TeleopPanel, self).hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowDeactivate and (
            self._motion_active() or self._pressed_keys
        ):
            self._stop_motion("window_deactivate")
        super(TeleopPanel, self).changeEvent(event)

    def _on_app_state_changed(self, state):
        if state == Qt.ApplicationActive:
            return
        if self._motion_active() or self._pressed_keys:
            self._stop_motion("application_inactive")
