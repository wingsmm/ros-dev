from __future__ import annotations

import math

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class RobotHudBar(QWidget):
    """Speed / pose / connection HUD; shared across workspace pages."""

    stop_motion_requested = pyqtSignal()

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
        self.warning_label = QLabel("")
        self.speed_label = QLabel("线速度 (vx): -- m/s")
        self.turn_label = QLabel("角速度 (wz): -- °/s")
        self.pose_label = QLabel("位姿 (x,y,yaw): --")

        for label in (
            self.conn_label,
            self.warning_label,
            self.speed_label,
            self.turn_label,
            self.pose_label,
        ):
            label.setStyleSheet("font-size: 13px; color: #333;")
            layout.addWidget(label)
        self.warning_label.hide()

        layout.addStretch(1)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedHeight(32)
        self.stop_btn.setStyleSheet(
            "QPushButton { background: #c62828; color: white; border: none;"
            " padding: 0 14px; border-radius: 4px; font-weight: 600; }"
            "QPushButton:hover { background: #b71c1c; }"
        )
        self.stop_btn.clicked.connect(self.stop_motion_requested.emit)
        layout.addWidget(self.stop_btn)
        self._base_style = (
            "background: #f0f0f0; border-bottom: 1px solid #ddd; padding: 4px;"
        )

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

    def set_warning_state(
        self,
        enabled: bool,
        warn_amount: float,
        front_min_m: float,
        safemode: bool,
        scale: float,
        *,
        scan_stale: bool = False,
    ) -> None:
        if not enabled:
            self.warning_label.hide()
            self.setStyleSheet(self._base_style)
            return

        warn = max(0.0, min(1.0, float(warn_amount)))
        if scan_stale:
            self.warning_label.setText("雷达超时")
            self.warning_label.setStyleSheet(
                "font-size: 13px; color: #e65100; font-weight: 600;"
            )
            self.warning_label.show()
            self.setStyleSheet(self._base_style)
            return

        self.warning_label.hide()
        if warn <= 0.0:
            self.setStyleSheet(self._base_style)
            return

        parts = []
        if math.isfinite(front_min_m):
            parts.append(f"前方障碍 {front_min_m:.2f}m")
        if safemode and scale < 0.999:
            parts.append(f"SafeMode scale {scale:.2f}")
        if parts:
            self.warning_label.setText(" | ".join(parts))
            self.warning_label.setStyleSheet(
                "font-size: 13px; color: #b71c1c; font-weight: 600;"
            )
            self.warning_label.show()

        red = int(240 + 15 * warn)
        green = int(240 * (1.0 - 0.65 * warn))
        blue = int(240 * (1.0 - 0.65 * warn))
        self.setStyleSheet(
            f"background: rgb({red},{green},{blue});"
            " border-bottom: 1px solid #ddd; padding: 4px;"
        )

    def set_warning_amount(self, amount: float) -> None:
        self.set_warning_state(
            enabled=True,
            warn_amount=amount,
            front_min_m=float("inf"),
            safemode=False,
            scale=1.0,
        )
