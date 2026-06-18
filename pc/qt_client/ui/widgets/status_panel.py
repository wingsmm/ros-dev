from __future__ import annotations

from typing import Any, Dict

from PyQt5.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from ui.widgets.robot_telemetry_panel import RobotTelemetryPanel


class StatusPanel(QWidget):
    """Legacy debug console: connection stats + JSON telemetry."""

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

        self._telemetry = RobotTelemetryPanel()
        root.addWidget(self._telemetry)
        root.addStretch(1)

    def set_connection(self, connected: bool, detail: str) -> None:
        self.conn_label.setText(detail if connected else "未连接")

    def set_control_state(self, state: str, last_send: str, last_feedback: str) -> None:
        self.control_label.setText(state)
        self.last_send_label.setText(last_send)
        self.last_feedback_label.setText(last_feedback)

    def update_base_status(self, msg: Dict[str, Any]) -> None:
        self._telemetry.update_base_status(msg)

    def update_odom(self, msg: Dict[str, Any]) -> None:
        self._telemetry.update_odom(msg)
