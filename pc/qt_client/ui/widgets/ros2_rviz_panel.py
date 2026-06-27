from __future__ import annotations

import time
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.ros2_bridge_manager import Ros2BridgeManager, Ros2RvizPanelSnapshot
from core.robot_frames import (
    BASE_FRAME,
    LASER_FRAME,
    ODOM_FRAME,
    robot_frames_summary,
)
from core.ros2_runtime import diagnostic_shell_commands


def _format_source_age(stamp_ms: int) -> str:
    if stamp_ms <= 0:
        return "—"
    age_sec = max(0.0, time.time() - stamp_ms / 1000.0)
    if age_sec < 1.0:
        return "刚刚"
    if age_sec < 60.0:
        return f"{age_sec:.0f}s 前"
    return f"{age_sec / 60.0:.1f}min 前"


def _format_hz(hz_map: dict, topic: str) -> str:
    value = hz_map.get(topic)
    if value is None:
        return "—"
    if value <= 0.01:
        return "0 Hz"
    return f"{value:.1f} Hz"


class Ros2RvizPanel(QWidget):
    """Robot page: ROS2 bridge + RViz2 debug controls."""

    def __init__(
        self,
        manager: Optional[Ros2BridgeManager] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._labels: dict[str, QLabel] = {}
        self._build_ui()
        self._wire_button_signals()
        self._wire_manager_signals()
        self.refresh_display()

    def set_manager(self, manager: Optional[Ros2BridgeManager]) -> None:
        if self._manager is manager:
            return
        if self._manager is not None:
            try:
                self._manager.snapshot_updated.disconnect(self._on_snapshot)
                self._manager.action_message.disconnect(self._on_action_message)
            except TypeError:
                pass
        self._manager = manager
        self._wire_manager_signals()
        self.refresh_display()

    def refresh_display(self) -> None:
        if self._manager is None:
            self._apply_snapshot(None)
            return
        self._apply_snapshot(self._manager.snapshot())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._collapse_btn = QToolButton()
        self._collapse_btn.setText("ROS2 / RViz2 联调")
        self._collapse_btn.setCheckable(True)
        self._collapse_btn.setChecked(False)
        self._collapse_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._collapse_btn.setArrowType(Qt.DownArrow)
        self._collapse_btn.setStyleSheet(
            "QToolButton { font-weight: 600; padding: 4px 2px; border: none; }"
        )
        self._collapse_btn.toggled.connect(self._on_collapse_toggled)
        root.addWidget(self._collapse_btn)

        self._body = QWidget()
        self._body.setVisible(False)
        self._collapse_btn.setArrowType(Qt.RightArrow)
        layout = QVBoxLayout(self._body)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        row1 = QHBoxLayout()
        self._bridge_start_btn = QPushButton("启动 ROS2 Bridge")
        self._bridge_stop_btn = QPushButton("停止")
        self._rviz_start_btn = QPushButton("启动 RViz2")
        self._rviz_stop_btn = QPushButton("停止")
        self._refresh_btn = QPushButton("刷新 topic 状态")
        self._copy_btn = QPushButton("复制诊断命令")
        for btn in (
            self._bridge_start_btn,
            self._bridge_stop_btn,
            self._rviz_start_btn,
            self._rviz_stop_btn,
            self._refresh_btn,
            self._copy_btn,
        ):
            row1.addWidget(btn)
        row1.addStretch(1)
        layout.addLayout(row1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        rows = [
            ("ros2_env", "ROS2 环境"),
            ("json_gateway", "JSON 网关"),
            ("origin", "Odom 原点"),
            ("bridge", "Bridge 进程"),
            ("scan_src", "laser_scan 源"),
            ("odom_src", "odom_base 源"),
            ("odom_raw_src", "odom_raw 源"),
            ("odom_laser_src", "odom_laser 源"),
            ("scan_hz", "/scan 发布"),
            ("odom_raw_hz", "/odom_raw 发布"),
            ("odom_hz", "/odom 发布"),
            ("odom_laser_hz", "/odom_laser 发布"),
            ("tf", "/tf /tf_static"),
            ("frames", "坐标链"),
            ("rviz", "RViz2"),
            ("error", "最近错误"),
        ]
        for row, (key, title) in enumerate(rows):
            title_lbl = QLabel(title + ":")
            title_lbl.setStyleSheet("color: #555;")
            value_lbl = QLabel("—")
            value_lbl.setWordWrap(True)
            self._labels[key] = value_lbl
            grid.addWidget(title_lbl, row, 0)
            grid.addWidget(value_lbl, row, 1)
        layout.addLayout(grid)

        hint = QLabel(
            "Odom 原点：连接后首帧 odom_base。"
            "本页 Bridge 仅发布激光/里程计/TF；摄像头仿真见「摄像头」页。"
            "RViz2 请点「启动 RViz2」手动打开。"
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        root.addWidget(self._body)

    def _on_collapse_toggled(self, expanded: bool) -> None:
        self._body.setVisible(expanded)
        self._collapse_btn.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )

    def _wire_button_signals(self) -> None:
        self._bridge_start_btn.clicked.connect(self._on_start_bridge)
        self._bridge_stop_btn.clicked.connect(self._on_stop_bridge)
        self._rviz_start_btn.clicked.connect(self._on_start_rviz)
        self._rviz_stop_btn.clicked.connect(self._on_stop_rviz)
        self._refresh_btn.clicked.connect(self._on_refresh_topics)
        self._copy_btn.clicked.connect(self._on_copy_diagnostics)

    def _wire_manager_signals(self) -> None:
        if self._manager is None:
            return
        self._manager.snapshot_updated.connect(self._on_snapshot)
        self._manager.action_message.connect(self._on_action_message)

    def _on_start_bridge(self) -> None:
        if self._manager is not None:
            self._manager.start_bridge()

    def _on_stop_bridge(self) -> None:
        if self._manager is not None:
            self._manager.stop_bridge()

    def _on_start_rviz(self) -> None:
        if self._manager is not None:
            self._manager.start_robot_rviz()

    def _on_stop_rviz(self) -> None:
        if self._manager is not None:
            self._manager.stop_rviz()

    def _on_refresh_topics(self) -> None:
        if self._manager is not None:
            self._manager.refresh_topic_status()

    def _on_copy_diagnostics(self) -> None:
        QGuiApplication.clipboard().setText(diagnostic_shell_commands())
        self._labels["error"].setText("诊断命令已复制到剪贴板")

    def _on_snapshot(self, snapshot: object) -> None:
        if isinstance(snapshot, Ros2RvizPanelSnapshot):
            self._apply_snapshot(snapshot)

    def _on_action_message(self, text: str) -> None:
        self._labels["error"].setText(text)

    def _apply_snapshot(self, snapshot: Optional[Ros2RvizPanelSnapshot]) -> None:
        if snapshot is None:
            for lbl in self._labels.values():
                lbl.setText("—")
            self._labels["error"].setText("未连接 RobotSession")
            return

        env = snapshot.env
        env_parts = []
        if env.distro:
            env_parts.append(env.distro)
        env_parts.append(f"DOMAIN_ID={env.domain_id}")
        env_parts.append("rclpy OK" if env.rclpy_ok else "rclpy 缺失")
        env_parts.append("numpy OK" if env.numpy_ok else "numpy 缺失")
        env_parts.append("rviz2 OK" if env.rviz2_ok else "rviz2 缺失")
        self._labels["ros2_env"].setText(" | ".join(env_parts))

        self._labels["json_gateway"].setText(
            "已连接" if snapshot.json_connected else "未连接"
        )

        origin_text = snapshot.origin_policy or "—"
        if snapshot.origin_summary:
            origin_text += f" | {snapshot.origin_summary}"
        self._labels["origin"].setText(origin_text)

        bridge = snapshot.bridge_status
        bridge_text = "运行中" if snapshot.bridge_running else "未运行"
        if bridge.last_error:
            bridge_text += f" ({bridge.last_error})"
        self._labels["bridge"].setText(bridge_text)

        src = bridge.last_source_ms
        self._labels["scan_src"].setText(_format_source_age(src.get("laser_scan", 0)))
        self._labels["odom_src"].setText(_format_source_age(src.get("odom_base", 0)))
        self._labels["odom_raw_src"].setText(
            _format_source_age(src.get("odom_raw", 0))
        )
        self._labels["odom_laser_src"].setText(
            _format_source_age(src.get("odom_laser", 0))
        )

        hz = bridge.publish_hz
        self._labels["scan_hz"].setText(_format_hz(hz, "/scan"))
        self._labels["odom_raw_hz"].setText(_format_hz(hz, "/odom_raw"))
        self._labels["odom_hz"].setText(_format_hz(hz, "/odom"))
        self._labels["odom_laser_hz"].setText(_format_hz(hz, "/odom_laser"))

        tf_parts = []
        tf_parts.append(
            f"{ODOM_FRAME}→{BASE_FRAME} OK"
            if bridge.tf_dynamic_ok
            else f"{ODOM_FRAME}→{BASE_FRAME} 待数据"
        )
        tf_parts.append(
            f"{BASE_FRAME}→{LASER_FRAME} OK"
            if bridge.tf_static_ok
            else f"{BASE_FRAME}→{LASER_FRAME} 未发"
        )
        self._labels["tf"].setText(" | ".join(tf_parts))
        self._labels["frames"].setText(robot_frames_summary())

        rviz_text = "运行中" if snapshot.rviz_running else "未运行"
        if snapshot.rviz_error:
            rviz_text += f" ({snapshot.rviz_error})"
        self._labels["rviz"].setText(rviz_text)

        if snapshot.topic_probe:
            self._labels["error"].setText(snapshot.topic_probe)
        elif bridge.last_error:
            self._labels["error"].setText(bridge.last_error)
        elif snapshot.rviz_error and not snapshot.rviz_running:
            self._labels["error"].setText(snapshot.rviz_error)
        elif env.errors:
            self._labels["error"].setText(env.format_report())
        else:
            self._labels["error"].setText("—")

        bridge_running = snapshot.bridge_running
        rviz_running = snapshot.rviz_running
        self._bridge_start_btn.setEnabled(not bridge_running)
        self._bridge_stop_btn.setEnabled(bridge_running)
        self._rviz_start_btn.setEnabled(not rviz_running)
        self._rviz_stop_btn.setEnabled(rviz_running)
