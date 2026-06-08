from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget


class StatusPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        conn_group = QGroupBox("连接与控制")
        conn_form = QFormLayout(conn_group)
        self.conn_label = QLabel("未连接")
        self.control_label = QLabel("失联")
        self.last_send_label = QLabel("-")
        self.last_feedback_label = QLabel("-")
        conn_form.addRow("连接", self.conn_label)
        conn_form.addRow("控制权", self.control_label)
        conn_form.addRow("最近发送", self.last_send_label)
        conn_form.addRow("最近反馈", self.last_feedback_label)
        root.addWidget(conn_group)

        status_group = QGroupBox("base_status")
        status_form = QFormLayout(status_group)
        self.online_label = QLabel("-")
        self.estop_label = QLabel("-")
        self.battery_label = QLabel("-")
        self.mode_label = QLabel("-")
        self.error_label = QLabel("-")
        status_form.addRow("online", self.online_label)
        status_form.addRow("estop", self.estop_label)
        status_form.addRow("battery_v", self.battery_label)
        status_form.addRow("mode", self.mode_label)
        status_form.addRow("error_code", self.error_label)
        root.addWidget(status_group)

        odom_group = QGroupBox("odom_base")
        odom_form = QFormLayout(odom_group)
        self.x_label = QLabel("-")
        self.y_label = QLabel("-")
        self.yaw_label = QLabel("-")
        self.vx_label = QLabel("-")
        self.vy_label = QLabel("-")
        self.wz_label = QLabel("-")
        odom_form.addRow("x", self.x_label)
        odom_form.addRow("y", self.y_label)
        odom_form.addRow("yaw", self.yaw_label)
        odom_form.addRow("vx", self.vx_label)
        odom_form.addRow("vy", self.vy_label)
        odom_form.addRow("wz", self.wz_label)
        root.addWidget(odom_group)
        root.addStretch(1)

    def set_connection(self, connected: bool, detail: str) -> None:
        self.conn_label.setText(detail if connected else "未连接")

    def set_control_state(self, state: str, last_send: str, last_feedback: str) -> None:
        self.control_label.setText(state)
        self.last_send_label.setText(last_send)
        self.last_feedback_label.setText(last_feedback)

    def update_base_status(self, msg: Dict[str, Any]) -> None:
        self.online_label.setText(self._fmt(msg.get("online")))
        self.estop_label.setText(self._fmt(msg.get("estop")))
        battery = msg.get("battery_v")
        self.battery_label.setText("-" if battery is None else "{:.2f} V".format(battery))
        self.mode_label.setText(self._fmt(msg.get("mode")))
        self.error_label.setText(self._fmt(msg.get("error_code")))

    def update_odom(self, msg: Dict[str, Any]) -> None:
        self.x_label.setText(self._fmt_num(msg.get("x")))
        self.y_label.setText(self._fmt_num(msg.get("y")))
        self.yaw_label.setText(self._fmt_num(msg.get("yaw")))
        self.vx_label.setText(self._fmt_num(msg.get("linear_x")))
        self.vy_label.setText(self._fmt_num(msg.get("linear_y")))
        self.wz_label.setText(self._fmt_num(msg.get("angular_z")))

    @staticmethod
    def _fmt(value: Any) -> str:
        return "-" if value is None else str(value)

    @staticmethod
    def _fmt_num(value: Optional[float]) -> str:
        if value is None:
            return "-"
        return "{:.3f}".format(float(value))
