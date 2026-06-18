from __future__ import annotations

from typing import Any, Dict

from PyQt5.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gateway.json_telemetry import format_base_status_display, format_odom_display


class RobotTelemetryPanel(QWidget):
    """JSON gateway feedback: base_status + odom_base (shared by new Shell and legacy)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)

        status_group = QGroupBox("base_status")
        status_form = QFormLayout(status_group)
        self.online_label = QLabel("-")
        self.estop_label = QLabel("-")
        self.battery_label = QLabel("-")
        self.mode_label = QLabel("-")
        self.error_label = QLabel("-")
        status_form.addRow("online (连接)", self.online_label)
        status_form.addRow("estop (急停)", self.estop_label)
        status_form.addRow("battery_v (电压)", self.battery_label)
        status_form.addRow("mode (模式)", self.mode_label)
        status_form.addRow("error_code (故障码)", self.error_label)
        row.addWidget(status_group, 1)

        odom_group = QGroupBox("odom_base")
        odom_form = QFormLayout(odom_group)
        self.x_label = QLabel("-")
        self.y_label = QLabel("-")
        self.yaw_label = QLabel("-")
        self.vx_label = QLabel("-")
        self.vy_label = QLabel("-")
        self.wz_label = QLabel("-")
        odom_form.addRow("x (位置X, m)", self.x_label)
        odom_form.addRow("y (位置Y, m)", self.y_label)
        odom_form.addRow("yaw (航向, °)", self.yaw_label)
        odom_form.addRow("vx (线速X, m/s)", self.vx_label)
        odom_form.addRow("vy (线速Y, m/s)", self.vy_label)
        odom_form.addRow("wz (角速度, °/s)", self.wz_label)
        row.addWidget(odom_group, 1)

        root.addLayout(row)

    def clear(self) -> None:
        self.update_base_status({})
        self.update_odom({})

    def update_base_status(self, msg: Dict[str, Any]) -> None:
        view = format_base_status_display(msg)
        self.online_label.setText(view.online)
        self.estop_label.setText(view.estop)
        self.battery_label.setText(view.battery_v)
        self.mode_label.setText(view.mode)
        self.error_label.setText(view.error_code)
        self._apply_battery_style(msg.get("battery_v"))
        self._apply_estop_style(msg.get("estop"))

    def update_odom(self, msg: Dict[str, Any]) -> None:
        view = format_odom_display(msg)
        self.x_label.setText(view.x_m)
        self.y_label.setText(view.y_m)
        self.yaw_label.setText(view.yaw_deg)
        self.vx_label.setText(view.vx_mps)
        self.vy_label.setText(view.vy_mps)
        self.wz_label.setText(view.wz_deg_s)

    def _apply_battery_style(self, battery: Any) -> None:
        if battery is None:
            self.battery_label.setStyleSheet("")
            return
        try:
            value = float(battery)
        except (TypeError, ValueError):
            self.battery_label.setStyleSheet("")
            return
        if value < 11.0:
            self.battery_label.setStyleSheet("color: #c62828; font-weight: 600;")
        elif value < 11.5:
            self.battery_label.setStyleSheet("color: #ef6c00;")
        else:
            self.battery_label.setStyleSheet("color: #2e7d32;")

    def _apply_estop_style(self, estop: Any) -> None:
        if estop is True:
            self.estop_label.setStyleSheet("color: #c62828; font-weight: 600;")
        else:
            self.estop_label.setStyleSheet("")
