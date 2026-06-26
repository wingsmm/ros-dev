from __future__ import annotations

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

from core.camera_ros2_bridge_manager import (
    CameraRos2BridgeManager,
    CameraRos2PanelSnapshot,
)
from core.camera_topics import CAMERA_DIAGNOSTIC_TOPICS
from core.robot_frames import (
    BASE_FRAME,
    CAMERA_FRAME,
    camera_frames_summary,
)
from core.ros2_runtime import rviz_rgbd_camera_config_path


def _format_hz(hz_map: dict, topic: str) -> str:
    value = hz_map.get(topic)
    if value is None:
        return "—"
    if value <= 0.01:
        return "0 Hz"
    return f"{value:.1f} Hz"


def _topic_status_text(snapshot: CameraRos2PanelSnapshot, topic: str) -> str:
    result = snapshot.topic_probe_result
    if result is not None:
        entry = result.entries.get(topic)
        if entry is not None:
            return entry.detail if entry.online else "离线"
    if topic == "/camera/image_raw" and snapshot.bridge_running:
        return _format_hz(snapshot.bridge_status.publish_hz, topic)
    return "—"


class CameraRos2Panel(QWidget):
    """Camera module: MJPEG bridge, RGB-D topic status, RViz2 entry."""

    def __init__(
        self,
        manager: Optional[CameraRos2BridgeManager] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._labels: dict[str, QLabel] = {}
        self._topic_labels: dict[str, QLabel] = {}
        self._build_ui()
        self._wire_button_signals()
        self._wire_manager_signals()
        self.refresh_display()

    def set_manager(self, manager: Optional[CameraRos2BridgeManager]) -> None:
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
        self._collapse_btn.setText("ROS2 / RViz2 诊断（摄像头）")
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
        self._bridge_start_btn = QPushButton("启动 Camera Bridge")
        self._bridge_stop_btn = QPushButton("停止 Bridge")
        self._rviz_start_btn = QPushButton("启动 RViz2")
        self._rviz_stop_btn = QPushButton("停止 RViz2")
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
            ("mjpeg_url", "MJPEG 源"),
            ("bridge", "Bridge 进程"),
            ("rviz", "RViz2"),
            ("tf", "/tf_static"),
            ("frames", "坐标链"),
            ("error", "最近状态"),
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

        topic_title = QLabel("RGB-D topic 状态（仅诊断，不改导航）")
        topic_title.setStyleSheet("font-weight: 600; color: #444; margin-top: 4px;")
        layout.addWidget(topic_title)

        topic_grid = QGridLayout()
        topic_grid.setHorizontalSpacing(12)
        topic_grid.setVerticalSpacing(2)
        for row, topic in enumerate(CAMERA_DIAGNOSTIC_TOPICS):
            name = QLabel(topic + ":")
            name.setStyleSheet("color: #555; font-size: 11px;")
            value = QLabel("—")
            value.setStyleSheet("font-size: 11px;")
            self._topic_labels[topic] = value
            topic_grid.addWidget(name, row, 0, Qt.AlignTop)
            topic_grid.addWidget(value, row, 1)
        layout.addLayout(topic_grid)

        rviz_cfg = rviz_rgbd_camera_config_path()
        hint = QLabel(
            "Phase 1 仅展示与诊断：RGB 预览仍走上方 MJPEG；"
            "Camera Bridge 手动启动后发布 /camera/image_raw 与 TF。"
            f"RViz2 使用 {rviz_cfg.name}（TF / PointCloud2 / LaserScan / Camera）。"
            "WSL2 下 RViz OpenGL 可能不稳定；原生 Linux 优先验收。"
            "/scan 仍来自主雷达，不把 /camera/scan_depth 接入导航。"
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
        if self._manager is not None:
            self._manager.set_diagnostics_expanded(expanded)
            if expanded:
                self._manager.refresh_topic_status()

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
            self._manager.start_rviz()

    def _on_stop_rviz(self) -> None:
        if self._manager is not None:
            self._manager.stop_rviz()

    def _on_refresh_topics(self) -> None:
        if self._manager is not None:
            self._manager.refresh_topic_status()

    def _on_copy_diagnostics(self) -> None:
        if self._manager is not None:
            QGuiApplication.clipboard().setText(
                self._manager.diagnostic_commands()
            )
        self._labels["error"].setText("诊断命令已复制到剪贴板")

    def _on_snapshot(self, snapshot: object) -> None:
        if isinstance(snapshot, CameraRos2PanelSnapshot):
            self._apply_snapshot(snapshot)

    def _on_action_message(self, text: str) -> None:
        self._labels["error"].setText(text)

    def _apply_snapshot(self, snapshot: Optional[CameraRos2PanelSnapshot]) -> None:
        if snapshot is None:
            for lbl in self._labels.values():
                lbl.setText("—")
            for lbl in self._topic_labels.values():
                lbl.setText("—")
            self._labels["error"].setText("未绑定 Camera Bridge")
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

        self._labels["mjpeg_url"].setText(snapshot.mjpeg_url or "—")

        bridge = snapshot.bridge_status
        bridge_text = "运行中" if snapshot.bridge_running else "未运行"
        if bridge.last_error:
            bridge_text += f" ({bridge.last_error})"
        self._labels["bridge"].setText(bridge_text)

        tf_text = (
            f"{BASE_FRAME}→{CAMERA_FRAME} OK"
            if bridge.tf_static_ok
            else f"{BASE_FRAME}→{CAMERA_FRAME} 未发"
        )
        self._labels["tf"].setText(tf_text)
        self._labels["frames"].setText(camera_frames_summary())

        rviz_text = "运行中" if snapshot.rviz_running else "未运行"
        if snapshot.rviz_error:
            rviz_text += f" ({snapshot.rviz_error})"
        self._labels["rviz"].setText(rviz_text)

        for topic, lbl in self._topic_labels.items():
            lbl.setText(_topic_status_text(snapshot, topic))

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
