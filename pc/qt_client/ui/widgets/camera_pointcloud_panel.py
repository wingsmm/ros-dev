from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from core.camera_topic_probe import CameraTopicProbeEntry, CameraTopicProbeResult
from core.camera_topics import (
    CAMERA_DEPTH_IMAGE_TOPIC,
    CAMERA_DEPTH_INFO_TOPIC,
    CAMERA_DEPTH_POINTS_TOPIC,
)


class CameraPointCloudPanel(QWidget):
    """Depth PointCloud2 diagnostic status (no nav coupling)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        title = QLabel("PointCloud2 点云（仅诊断，不改导航）")
        title.setStyleSheet("font-weight: 600; color: #333;")
        root.addWidget(title)

        hint = QLabel(
            "深度点云用于检查相机姿态、地面平面和 TF；不接 RGB，不接导航。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        rows = [
            ("depth_image", "深度图", CAMERA_DEPTH_IMAGE_TOPIC),
            ("depth_info", "相机内参", CAMERA_DEPTH_INFO_TOPIC),
            ("depth_points", "点云", CAMERA_DEPTH_POINTS_TOPIC),
        ]
        for row, (key, title_text, topic) in enumerate(rows):
            name = QLabel(f"{title_text}:")
            name.setStyleSheet("color: #555; font-size: 11px;")
            value = QLabel("—")
            value.setStyleSheet("font-size: 11px;")
            self._labels[key] = value
            grid.addWidget(name, row, 0, Qt.AlignTop)
            grid.addWidget(value, row, 1)
            sub = QLabel(topic)
            sub.setStyleSheet("color: #888; font-size: 10px;")
            grid.addWidget(sub, row, 2, Qt.AlignTop)
        root.addLayout(grid)

    def apply_probe(self, result: Optional[CameraTopicProbeResult]) -> None:
        if result is None:
            for lbl in self._labels.values():
                lbl.setText("—")
            return
        self._labels["depth_image"].setText(
            _format_entry(result.entries.get(CAMERA_DEPTH_IMAGE_TOPIC))
        )
        self._labels["depth_info"].setText(
            _format_entry(result.entries.get(CAMERA_DEPTH_INFO_TOPIC))
        )
        self._labels["depth_points"].setText(
            _format_entry(result.entries.get(CAMERA_DEPTH_POINTS_TOPIC))
        )


def _format_entry(entry: Optional[CameraTopicProbeEntry]) -> str:
    if entry is None:
        return "—"
    if entry.online:
        return f"在线 — {entry.detail}"
    return "离线"
