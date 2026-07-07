"""Dead-man /cmd_vel teleop panel, aligned with vmware/qt."""

from __future__ import annotations

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
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

    def __init__(
        self,
        linear_speed: float = 1.0,
        angular_speed: float = 1.0,
        repeat_hz: int = 10,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._linear = float(linear_speed)
        self._angular = float(angular_speed)
        self._active_velocity = (0.0, 0.0, 0.0)
        self._controls_enabled = True
        self._keyboard_enabled = False
        self._pressed_keys: set[int] = set()
        self._repeat_timer = QTimer(self)
        interval_ms = max(50, int(1000.0 / max(1, repeat_hz)))
        self._repeat_timer.setInterval(interval_ms)
        self._repeat_timer.timeout.connect(self._repeat_active_velocity)
        self._buttons: list[QPushButton] = []
        self.setFocusPolicy(Qt.StrongFocus)
        self._build_ui()

        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    def set_keyboard_enabled(self, enabled: bool) -> None:
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
                self._stop_motion()
        elif window is not None:
            window.installEventFilter(self)
        self._hint_label.setText(self._default_hint())

    def set_controls_enabled(self, enabled: bool, reason: str = "") -> None:
        self._controls_enabled = bool(enabled)
        for button in self._buttons:
            button.setEnabled(self._controls_enabled)
        if not self._controls_enabled:
            self.set_keyboard_enabled(False)
            self._stop_motion()
            self._hint_label.setText(reason or "ROS2 未就绪，遥控已禁用。")
        else:
            self._hint_label.setText(self._default_hint())

    def stop(self) -> None:
        if self._motion_active() or self._pressed_keys:
            self._stop_motion()

    def _default_hint(self) -> str:
        keyboard = ""
        if self._keyboard_enabled:
            keyboard = " 键盘：W/↑ 前进，S/↓ 后退，A/Q/← 左转，D/E/→ 右转，K/Space 停止。"
        return (
            "按住运动、松开停止（约 10Hz 重发）。左/右为原地转向；"
            "这里只发布 ROS2 /cmd_vel 干跑，不调用 car_web。"
            + keyboard
        )

    def _motion_active(self) -> bool:
        return self._repeat_timer.isActive()

    def _build_ui(self) -> None:
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
            button = QPushButton(text)
            button.setMinimumHeight(42)
            button.setAutoRepeat(False)
            self._buttons.append(button)
            if is_stop:
                button.setStyleSheet(
                    "QPushButton { background: #c62828; color: white; font-weight: 600; }"
                )
                button.clicked.connect(handler)
            else:
                button.pressed.connect(handler)
                button.released.connect(self._on_button_released)
            grid.addWidget(button, row, col)

        self._hint_label = QLabel(self._default_hint())
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet("color: #666; font-size: 11px;")

        group_layout = QVBoxLayout()
        group_layout.addLayout(grid)
        group_layout.addWidget(self._hint_label)
        group.setLayout(group_layout)
        root.addWidget(group)

    def _emit_vel(self, lx: float, ly: float, az: float) -> None:
        if not self._controls_enabled:
            return
        self._active_velocity = (lx, ly, az)
        self.velocity_requested.emit(lx, ly, az)
        if not self._repeat_timer.isActive():
            self._repeat_timer.start()

    def _repeat_active_velocity(self) -> None:
        lx, ly, az = self._active_velocity
        self.velocity_requested.emit(lx, ly, az)

    def _on_stop_button(self) -> None:
        self._stop_motion()

    def _stop_motion(self) -> None:
        had_motion = self._motion_active() or bool(self._pressed_keys)
        self._repeat_timer.stop()
        self._active_velocity = (0.0, 0.0, 0.0)
        self._pressed_keys.clear()
        if had_motion:
            self.stop_requested.emit()

    def _on_button_released(self) -> None:
        if self._pressed_keys and self._keyboard_enabled:
            self._apply_keyboard_motion()
            return
        if self._motion_active():
            self._stop_motion()

    @staticmethod
    def _focus_in_text_input() -> bool:
        widget = QApplication.focusWidget()
        return isinstance(widget, _TEXT_INPUT_TYPES)

    def _should_handle_keyboard(self) -> bool:
        return (
            self._keyboard_enabled
            and self._controls_enabled
            and self.isVisible()
            and not self._focus_in_text_input()
        )

    def _keyboard_velocity(self) -> tuple[float, float, float]:
        lx = az = 0.0
        forward = bool(self._pressed_keys & _FORWARD_KEYS)
        back = bool(self._pressed_keys & _BACK_KEYS)
        if forward and not back:
            lx = self._linear
        elif back and not forward:
            lx = -self._linear

        turn_left = bool(self._pressed_keys & _TURN_LEFT_KEYS)
        turn_right = bool(self._pressed_keys & _TURN_RIGHT_KEYS)
        if turn_left and not turn_right:
            az = self._angular
        elif turn_right and not turn_left:
            az = -self._angular
        return lx, 0.0, az

    def _apply_keyboard_motion(self) -> None:
        if not self._pressed_keys:
            if self._motion_active():
                self._stop_motion()
            return
        lx, ly, az = self._keyboard_velocity()
        if lx == 0.0 and ly == 0.0 and az == 0.0:
            if self._motion_active():
                self._stop_motion()
            return
        self._emit_vel(lx, ly, az)

    def _handle_key_press(self, event) -> bool:
        if not self._should_handle_keyboard():
            return False
        if event.isAutoRepeat():
            return True
        key = event.key()
        if key in _STOP_KEYS:
            self._stop_motion()
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

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.KeyPress and self._handle_key_press(event):
            return True
        if event.type() == QEvent.KeyRelease and self._handle_key_release(event):
            return True
        if event.type() == QEvent.WindowDeactivate and (
            self._motion_active() or self._pressed_keys
        ):
            self._stop_motion()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._handle_key_press(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._handle_key_release(event):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._motion_active() or self._pressed_keys:
            self._stop_motion()
        super().hideEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.type() == QEvent.WindowDeactivate and (
            self._motion_active() or self._pressed_keys
        ):
            self._stop_motion()
        super().changeEvent(event)

    def _on_app_state_changed(self, state) -> None:
        if state != Qt.ApplicationActive and (self._motion_active() or self._pressed_keys):
            self._stop_motion()
