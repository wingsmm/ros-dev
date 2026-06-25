from __future__ import annotations

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_STOP_KEYS = frozenset({Qt.Key_K, Qt.Key_Space})
_FORWARD_KEYS = frozenset({Qt.Key_W, Qt.Key_I})
_BACK_KEYS = frozenset({Qt.Key_S})
_STRAFE_LEFT_KEYS = frozenset({Qt.Key_A})
_STRAFE_RIGHT_KEYS = frozenset({Qt.Key_D})
_TURN_LEFT_KEYS = frozenset({Qt.Key_Q, Qt.Key_J})
_TURN_RIGHT_KEYS = frozenset({Qt.Key_E, Qt.Key_L})
_MOTION_KEYS = (
    _FORWARD_KEYS
    | _BACK_KEYS
    | _STRAFE_LEFT_KEYS
    | _STRAFE_RIGHT_KEYS
    | _TURN_LEFT_KEYS
    | _TURN_RIGHT_KEYS
)

_TEXT_INPUT_TYPES = (
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
)


class ManualControlStrip(QWidget):
    """Compact dead-man teleop; emits velocity signals only while held."""

    velocity_requested = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._linear = 0.10
        self._angular = 0.20
        self._active_velocity = (0.0, 0.0, 0.0)
        self._pressed_keys: set[int] = set()
        self._keyboard_enabled = False
        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(100)
        self._repeat_timer.timeout.connect(self._repeat_active_velocity)
        self.setFocusPolicy(Qt.StrongFocus)
        self._build_ui()

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    def set_speeds(self, linear: float, angular: float) -> None:
        self._linear = float(linear)
        self._angular = float(angular)

    def set_keyboard_enabled(self, enabled: bool) -> None:
        if enabled == self._keyboard_enabled:
            return
        window = self.window()
        if self._keyboard_enabled and window is not None:
            window.removeEventFilter(self)
        self._keyboard_enabled = enabled
        if not enabled:
            self._pressed_keys.clear()
            self.stop()
            return
        if window is not None:
            window.installEventFilter(self)

    def keyboard_enabled(self) -> bool:
        return self._keyboard_enabled

    def _motion_active(self) -> bool:
        return self._repeat_timer.isActive()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        group = QGroupBox("手动遥控（按住才运动，松开即停止）")
        grid = QGridLayout()
        grid.setSpacing(6)

        actions = [
            (0, 1, "前进", lambda: self._emit_vel(self._linear, 0.0, 0.0), False),
            (2, 1, "后退", lambda: self._emit_vel(-self._linear, 0.0, 0.0), False),
            (1, 0, "左移", lambda: self._emit_vel(0.0, self._linear, 0.0), False),
            (1, 2, "右移", lambda: self._emit_vel(0.0, -self._linear, 0.0), False),
            (1, 1, "停止", self._on_stop_button, True),
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
                btn.pressed.connect(handler)
                btn.released.connect(self._on_button_released)
            grid.addWidget(btn, row, col)

        hint = QLabel(
            "键盘：W/I 前进，S 后退，A/D 左右平移，Q/J 左转，E/L 右转，K/Space 停止"
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)

        group_layout = QVBoxLayout()
        group_layout.addLayout(grid)
        group_layout.addWidget(hint)
        group.setLayout(group_layout)
        root.addWidget(group)

    def _emit_vel(self, lx: float, ly: float, az: float) -> None:
        self._active_velocity = (lx, ly, az)
        self.velocity_requested.emit(lx, ly, az)
        if not self._repeat_timer.isActive():
            self._repeat_timer.start()

    def _repeat_active_velocity(self) -> None:
        lx, ly, az = self._active_velocity
        self.velocity_requested.emit(lx, ly, az)

    def _on_stop_button(self) -> None:
        self._repeat_timer.stop()
        self._active_velocity = (0.0, 0.0, 0.0)
        self._pressed_keys.clear()
        self.stop_requested.emit()

    def _on_button_released(self) -> None:
        if self._pressed_keys and self._keyboard_enabled:
            self._apply_keyboard_motion()
            return
        if not self._motion_active():
            return
        self._on_stop_button()

    def stop(self) -> None:
        if self._motion_active() or self._pressed_keys:
            self._on_stop_button()

    def _keyboard_velocity(self) -> tuple[float, float, float]:
        lx = ly = az = 0.0
        forward = bool(self._pressed_keys & _FORWARD_KEYS)
        back = bool(self._pressed_keys & _BACK_KEYS)
        if forward and not back:
            lx += self._linear
        elif back and not forward:
            lx -= self._linear

        strafe_l = bool(self._pressed_keys & _STRAFE_LEFT_KEYS)
        strafe_r = bool(self._pressed_keys & _STRAFE_RIGHT_KEYS)
        if strafe_l and not strafe_r:
            ly += self._linear
        elif strafe_r and not strafe_l:
            ly -= self._linear

        turn_l = bool(self._pressed_keys & _TURN_LEFT_KEYS)
        turn_r = bool(self._pressed_keys & _TURN_RIGHT_KEYS)
        if turn_l and not turn_r:
            az += self._angular
        elif turn_r and not turn_l:
            az -= self._angular
        return lx, ly, az

    def _apply_keyboard_motion(self) -> None:
        if not self._pressed_keys:
            if self._motion_active():
                self._on_stop_button()
            return
        lx, ly, az = self._keyboard_velocity()
        if lx == 0.0 and ly == 0.0 and az == 0.0:
            if self._motion_active():
                self._on_stop_button()
            return
        self._emit_vel(lx, ly, az)

    @staticmethod
    def _focus_in_text_input() -> bool:
        widget = QApplication.focusWidget()
        if widget is None:
            return False
        return isinstance(widget, _TEXT_INPUT_TYPES)

    def _should_handle_keyboard(self) -> bool:
        return (
            self._keyboard_enabled
            and self.isVisible()
            and not self._focus_in_text_input()
        )

    def _handle_key_press(self, event) -> bool:
        if not self._should_handle_keyboard():
            return False
        if event.isAutoRepeat():
            return True
        key = event.key()
        if key in _STOP_KEYS:
            self._on_stop_button()
            return True
        if key not in _MOTION_KEYS:
            return False
        if key not in self._pressed_keys:
            self._pressed_keys.add(key)
            self._apply_keyboard_motion()
        return True

    def _handle_key_release(self, event) -> bool:
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

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress:
            if self._handle_key_press(event):
                return True
        elif event.type() == QEvent.KeyRelease:
            if self._handle_key_release(event):
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        if self._handle_key_press(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if self._handle_key_release(event):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def hideEvent(self, event) -> None:
        if self._motion_active() or self._pressed_keys:
            self.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        if self._motion_active() or self._pressed_keys:
            self.stop()
        super().closeEvent(event)

    def _on_app_state_changed(self, state: Qt.ApplicationState) -> None:
        if state != Qt.ApplicationActive and (
            self._motion_active() or self._pressed_keys
        ):
            self.stop()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.WindowDeactivate and (
            self._motion_active() or self._pressed_keys
        ):
            self.stop()
        super().changeEvent(event)
