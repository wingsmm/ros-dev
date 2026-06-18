from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class RobotHudBar(QWidget):
    """Speed / pose / connection HUD; shared across workspace pages."""

    emergency_stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.set_placeholder()

    def _build_ui(self) -> None:
        self.setFixedHeight(48)
        self.setStyleSheet(
            "background: #f0f0f0; border-bottom: 1px solid #ddd; padding: 4px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(16)

        self.conn_label = QLabel("未连接")
        self.speed_label = QLabel("线速度 (vx): -- m/s")
        self.turn_label = QLabel("角速度 (wz): -- °/s")
        self.pose_label = QLabel("位姿 (x,y,yaw): --")

        for label in (self.conn_label, self.speed_label, self.turn_label, self.pose_label):
            label.setStyleSheet("font-size: 13px; color: #333;")
            layout.addWidget(label)

        layout.addStretch(1)

        self.stop_btn = QPushButton("急停")
        self.stop_btn.setFixedHeight(32)
        self.stop_btn.setStyleSheet(
            "QPushButton { background: #c62828; color: white; border: none;"
            " padding: 0 14px; border-radius: 4px; font-weight: 600; }"
            "QPushButton:hover { background: #b71c1c; }"
        )
        self.stop_btn.clicked.connect(self.emergency_stop_requested.emit)
        layout.addWidget(self.stop_btn)

    def set_placeholder(self) -> None:
        self.set_connection(False, "占位")
        self.set_motion("--", "--")
        self.set_pose("--")

    def set_connection(self, connected: bool, detail: str = "") -> None:
        if connected:
            text = f"已连接 {detail}".strip()
            color = "#2e7d32"
        else:
            text = detail or "未连接"
            color = "#666"
        self.conn_label.setText(text)
        self.conn_label.setStyleSheet(f"font-size: 13px; color: {color};")

    def set_motion(self, linear: str, angular: str) -> None:
        self.speed_label.setText(f"线速度 (vx): {linear} m/s")
        self.turn_label.setText(f"角速度 (wz): {angular} °/s")

    def set_pose(self, pose_text: str) -> None:
        self.pose_label.setText(f"位姿 (x,y,yaw): {pose_text}")
