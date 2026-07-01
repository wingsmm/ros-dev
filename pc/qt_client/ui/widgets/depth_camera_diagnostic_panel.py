"""Merged depth diagnostic panel for the depth camera page."""

from __future__ import annotations

import math
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from core.camera_depth_frame import DepthFrameStats, DepthSourceKind
from core.camera_topic_probe import CameraTopicProbeEntry, CameraTopicProbeResult
from core.camera_topics import (
    CAMERA_DEPTH_IMAGE_TOPIC,
    CAMERA_DEPTH_INFO_TOPIC,
    CAMERA_DEPTH_POINTS_TOPIC,
)
from core.robot_frames import (
    CAMERA_OPTICAL_FRAME,
    CAMERA_PITCH,
    CAMERA_ROLL,
    CAMERA_X,
    CAMERA_Y,
    CAMERA_YAW,
    CAMERA_Z,
)
from core.ros2_bridge_manager import CameraRos2PanelSnapshot


def _compact_status_text(text: str, *, limit: int = 80) -> str:
    value = " ".join((text or "").split())
    if not value:
        return "—"
    return value if len(value) <= limit else value[: limit - 1] + "..."


class DepthCameraDiagnosticPanel(QWidget):
    """Right-side depth-only diagnostics: URL, topics, extrinsics, rates."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._topic_labels: dict[str, QLabel] = {}
        self._url_label = QLabel("—")
        self._frame_label = QLabel(CAMERA_OPTICAL_FRAME)
        self._extrinsic_label = QLabel("—")
        self._points_hz_label = QLabel("—")
        self._error_label = QLabel("—")
        self._raw_status_label = QLabel("未接入")
        self._build_ui()
        self._set_extrinsic_summary()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(6)

        title = QLabel("深度相机诊断")
        title.setStyleSheet("font-weight: 600; color: #333;")
        root.addWidget(title)

        self._raw_status_label.setStyleSheet("color: #666; font-size: 12px;")
        root.addWidget(self._raw_status_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        def add_row(row: int, caption: str, value_lbl: QLabel) -> None:
            name = QLabel(caption)
            name.setStyleSheet("color: #555; font-size: 11px;")
            value_lbl.setWordWrap(True)
            value_lbl.setStyleSheet("font-size: 11px; color: #333;")
            grid.addWidget(name, row, 0, Qt.AlignTop)
            grid.addWidget(value_lbl, row, 1)

        add_row(0, "Raw HTTP URL", self._url_label)
        rows = [
            ("depth_image", f"Raw topic: {CAMERA_DEPTH_IMAGE_TOPIC}"),
            ("depth_info", f"CameraInfo: {CAMERA_DEPTH_INFO_TOPIC}"),
            ("depth_points", f"PointCloud2: {CAMERA_DEPTH_POINTS_TOPIC}"),
        ]
        for offset, (key, caption) in enumerate(rows, start=1):
            lbl = QLabel("—")
            self._topic_labels[key] = lbl
            add_row(offset, caption, lbl)

        base = len(rows) + 1
        add_row(base, "frame", self._frame_label)
        add_row(base + 1, "外参 (base_link→camera)", self._extrinsic_label)
        add_row(base + 2, "点云发布频率", self._points_hz_label)
        add_row(base + 3, "最近状态", self._error_label)
        root.addLayout(grid)

    def _set_extrinsic_summary(self) -> None:
        roll = math.degrees(CAMERA_ROLL)
        pitch = math.degrees(CAMERA_PITCH)
        yaw = math.degrees(CAMERA_YAW)
        self._extrinsic_label.setText(
            f"x={CAMERA_X:.2f} y={CAMERA_Y:.2f} z={CAMERA_Z:.2f} m | "
            f"roll={roll:.0f}° pitch={pitch:.0f}° yaw={yaw:.0f}°"
        )

    def set_http_url(self, url: str) -> None:
        self._url_label.setText(url or "—")

    def set_raw_stream_status(self, text: str, kind: DepthSourceKind | str) -> None:
        self._raw_status_label.setText(f"Depth raw: {text}")
        if isinstance(kind, str):
            try:
                kind = DepthSourceKind(kind)
            except ValueError:
                kind = DepthSourceKind.OFFLINE
        suffix = ""
        if kind == DepthSourceKind.RAW_HTTP:
            suffix = " (raw-only)"
        self._raw_status_label.setText(f"Depth raw HTTP: {text}{suffix}")

    def apply_stats(self, stats: Optional[DepthFrameStats]) -> None:
        if stats is None:
            return
        info_lbl = self._topic_labels.get("depth_info")
        if info_lbl is not None:
            info_lbl.setText("online" if stats.camera_info_online else "offline")

    def apply_probe(self, result: Optional[CameraTopicProbeResult]) -> None:
        mapping = {
            "depth_image": CAMERA_DEPTH_IMAGE_TOPIC,
            "depth_info": CAMERA_DEPTH_INFO_TOPIC,
            "depth_points": CAMERA_DEPTH_POINTS_TOPIC,
        }
        if result is None:
            for lbl in self._topic_labels.values():
                lbl.setText("—")
            return
        for key, topic in mapping.items():
            lbl = self._topic_labels.get(key)
            if lbl is not None:
                lbl.setText(_format_entry(result.entries.get(topic)))
        tf_entry = result.entries.get("/tf_static")
        if tf_entry is not None and tf_entry.online:
            self._error_label.setText(tf_entry.detail or "/tf_static OK")

    def set_status_message(self, text: str) -> None:
        self._error_label.setText(_compact_status_text(text))

    def apply_bridge_snapshot(self, snapshot: Optional[CameraRos2PanelSnapshot]) -> None:
        if snapshot is None:
            self._points_hz_label.setText("—")
            return
        hz = snapshot.bridge_status.publish_hz.get(CAMERA_DEPTH_POINTS_TOPIC)
        if hz is not None and hz > 0.01:
            self._points_hz_label.setText(f"{hz:.1f} Hz")
        elif snapshot.bridge_running:
            self._points_hz_label.setText("等待首帧")
        else:
            self._points_hz_label.setText("Bridge 未运行")
        bridge = snapshot.bridge_status
        if bridge.last_error:
            self._error_label.setText(_compact_status_text(bridge.last_error))
        elif snapshot.topic_probe:
            self._error_label.setText(_compact_status_text(snapshot.topic_probe))
        elif snapshot.rviz_error and not snapshot.rviz_running:
            self._error_label.setText(_compact_status_text(snapshot.rviz_error))
        else:
            self._error_label.setText("—")


def _format_entry(entry: Optional[CameraTopicProbeEntry]) -> str:
    if entry is None:
        return "—"
    if entry.online:
        return f"online — {entry.detail}"
    return "offline"
