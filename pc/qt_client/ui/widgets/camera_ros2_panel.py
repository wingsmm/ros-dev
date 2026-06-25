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

from core.camera_ros2_bridge_manager import (
    CameraRos2BridgeManager,
    CameraRos2PanelSnapshot,
)
from core.robot_frames import (
    BASE_FRAME,
    CAMERA_FRAME,
    CAMERA_ROS_TOPIC,
    camera_frames_summary,
)


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


class CameraRos2Panel(QWidget):
    """Camera page: MJPEG -> ROS2 topic bridge (no RViz2 on this page)."""

    def __init__(
        self,
        manager: Optional[CameraRos2BridgeManager] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._labels: dict[str, QLabel] = {}
        self._build_ui()
        self._wire_signals()
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
        self._wire_signals()
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
        self._collapse_btn.setText("ROS2 联调（摄像头）")
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
        self._bridge_stop_btn = QPushButton("停止")
        self._refresh_btn = QPushButton("刷新 topic 状态")
        self._copy_btn = QPushButton("复制诊断命令")
        for btn in (
            self._bridge_start_btn,
            self._bridge_stop_btn,
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
            ("camera_hz", f"{CAMERA_ROS_TOPIC} 发布"),
            ("camera_src", "camera 源"),
            ("tf", "/tf_static"),
            ("frames", "坐标链"),
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
            "看图请用上方 Qt MJPEG 预览。"
            f"Camera Bridge 手动启动后发布 {CAMERA_ROS_TOPIC}（约 5fps）"
            f"与 {BASE_FRAME}→{CAMERA_FRAME} TF，用 ros2 topic 验收。"
            "本页不提供 RViz2：WSL2 下摄像头 RViz/OpenGL 不稳定，不作为验收项。"
            "原生 Linux 可参考 config/xtark_camera.rviz 手工调试。"
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

    def _wire_signals(self) -> None:
        self._bridge_start_btn.clicked.connect(self._on_start_bridge)
        self._bridge_stop_btn.clicked.connect(self._on_stop_bridge)
        self._refresh_btn.clicked.connect(self._on_refresh_topics)
        self._copy_btn.clicked.connect(self._on_copy_diagnostics)
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
            self._labels["error"].setText("未绑定 Camera Bridge")
            return

        env = snapshot.env
        env_parts = []
        if env.distro:
            env_parts.append(env.distro)
        env_parts.append(f"DOMAIN_ID={env.domain_id}")
        env_parts.append("rclpy OK" if env.rclpy_ok else "rclpy 缺失")
        env_parts.append("numpy OK" if env.numpy_ok else "numpy 缺失")
        self._labels["ros2_env"].setText(" | ".join(env_parts))

        self._labels["mjpeg_url"].setText(snapshot.mjpeg_url or "—")

        bridge = snapshot.bridge_status
        bridge_text = "运行中" if snapshot.bridge_running else "未运行"
        if bridge.last_error:
            bridge_text += f" ({bridge.last_error})"
        self._labels["bridge"].setText(bridge_text)

        src = bridge.last_source_ms
        hz = bridge.publish_hz
        self._labels["camera_hz"].setText(_format_hz(hz, CAMERA_ROS_TOPIC))
        cam_age = _format_source_age(src.get("camera_image", 0))
        cam_status = bridge.mjpeg_status or "—"
        self._labels["camera_src"].setText(
            f"{cam_age} | {cam_status}" if cam_age != "—" else cam_status
        )

        tf_text = (
            f"{BASE_FRAME}→{CAMERA_FRAME} OK"
            if bridge.tf_static_ok
            else f"{BASE_FRAME}→{CAMERA_FRAME} 未发"
        )
        self._labels["tf"].setText(tf_text)
        self._labels["frames"].setText(camera_frames_summary())

        if snapshot.topic_probe:
            self._labels["error"].setText(snapshot.topic_probe)
        elif bridge.last_error:
            self._labels["error"].setText(bridge.last_error)
        elif env.errors:
            self._labels["error"].setText(env.format_report())
        else:
            self._labels["error"].setText("—")

        bridge_running = snapshot.bridge_running
        self._bridge_start_btn.setEnabled(not bridge_running)
        self._bridge_stop_btn.setEnabled(bridge_running)
