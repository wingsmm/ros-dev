from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from core.camera_topic_probe import CameraTopicProbeEntry, CameraTopicProbeResult
from core.camera_topics import CAMERA_SCAN_DEPTH_TOPIC, MAIN_SCAN_TOPIC


class CameraScanPanel(QWidget):
    """Compare main /scan vs optional /camera/scan_depth (diagnostic only)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        title = QLabel("LaserScan 对比（仅诊断，不改导航）")
        title.setStyleSheet("font-weight: 600; color: #333;")
        root.addWidget(title)

        hint = QLabel(
            f"导航主链路仍使用 {MAIN_SCAN_TOPIC}；"
            f"{CAMERA_SCAN_DEPTH_TOPIC} 为深度转 scan 独立 topic。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        rows = [
            ("main_scan", MAIN_SCAN_TOPIC, "主雷达（导航）"),
            ("depth_scan", CAMERA_SCAN_DEPTH_TOPIC, "深度 scan（可选）"),
        ]
        for row, (key, topic, title_text) in enumerate(rows):
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
        self._labels["main_scan"].setText(
            _format_entry(result.entries.get(MAIN_SCAN_TOPIC))
        )
        self._labels["depth_scan"].setText(
            _format_entry(result.entries.get(CAMERA_SCAN_DEPTH_TOPIC))
        )


def _format_entry(entry: Optional[CameraTopicProbeEntry]) -> str:
    if entry is None:
        return "—"
    if entry.online:
        return f"在线 — {entry.detail}"
    return "离线"
