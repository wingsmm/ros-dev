from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ControlPanel(QWidget):
    velocity_changed = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        param_group = QGroupBox("速度参数")
        param_form = QFormLayout(param_group)
        self.linear_spin = QDoubleSpinBox()
        self.linear_spin.setRange(0.0, 0.30)
        self.linear_spin.setSingleStep(0.01)
        self.linear_spin.setDecimals(2)
        self.linear_spin.setValue(0.10)
        self.angular_spin = QDoubleSpinBox()
        self.angular_spin.setRange(0.0, 0.80)
        self.angular_spin.setSingleStep(0.01)
        self.angular_spin.setDecimals(2)
        self.angular_spin.setValue(0.20)
        self.timeout_hint = QLabel("bridge cmd_timeout ≈ 0.5 s，按住按钮/键盘才持续运动")
        self.timeout_hint.setWordWrap(True)
        param_form.addRow("线速度 m/s", self.linear_spin)
        param_form.addRow("角速度 rad/s", self.angular_spin)
        param_form.addRow("提示", self.timeout_hint)
        root.addWidget(param_group)

        move_group = QGroupBox("手动控制")
        grid = QGridLayout(move_group)
        self.btn_forward = QPushButton("前进 (W/I)")
        self.btn_back = QPushButton("后退 (S)")
        self.btn_left = QPushButton("左转 (A/J)")
        self.btn_right = QPushButton("右转 (D/L)")
        self.btn_strafe_l = QPushButton("左移 (Q)")
        self.btn_strafe_r = QPushButton("右移 (E)")
        self.btn_stop = QPushButton("停车 (K/Space)")
        self.btn_stop.setStyleSheet("font-weight: bold;")
        for btn in (
            self.btn_forward,
            self.btn_back,
            self.btn_left,
            self.btn_right,
            self.btn_strafe_l,
            self.btn_strafe_r,
        ):
            btn.setAutoRepeat(False)

        grid.addWidget(self.btn_forward, 0, 1)
        grid.addWidget(self.btn_strafe_l, 1, 0)
        grid.addWidget(self.btn_stop, 1, 1)
        grid.addWidget(self.btn_strafe_r, 1, 2)
        grid.addWidget(self.btn_back, 2, 1)
        grid.addWidget(self.btn_left, 3, 0)
        grid.addWidget(self.btn_right, 3, 2)

        hint = QLabel("键盘: W/S 前后, A/D 左右转, Q/E 横移, K/Space 停车; I/J/K/L 同向备用")
        hint.setWordWrap(True)
        root.addWidget(move_group)
        root.addWidget(hint)
        root.addStretch(1)

        self._wire_hold(self.btn_forward, lambda: self._emit_axis(lx=1))
        self._wire_hold(self.btn_back, lambda: self._emit_axis(lx=-1))
        self._wire_hold(self.btn_left, lambda: self._emit_axis(az=1))
        self._wire_hold(self.btn_right, lambda: self._emit_axis(az=-1))
        self._wire_hold(self.btn_strafe_l, lambda: self._emit_axis(ly=1))
        self._wire_hold(self.btn_strafe_r, lambda: self._emit_axis(ly=-1))
        self.btn_stop.clicked.connect(self.stop_requested.emit)

    def _wire_hold(self, button: QPushButton, factory):
        button.pressed.connect(factory)
        button.released.connect(self.stop_requested.emit)

    def linear_speed(self) -> float:
        return self.linear_spin.value()

    def angular_speed(self) -> float:
        return self.angular_spin.value()

    def _emit_axis(self, lx: int = 0, ly: int = 0, az: int = 0) -> None:
        self.velocity_changed.emit(
            lx * self.linear_speed(),
            ly * self.linear_speed(),
            az * self.angular_speed(),
        )
