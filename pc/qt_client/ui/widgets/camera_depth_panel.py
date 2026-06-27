from __future__ import annotations

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


class CameraDepthPanel(QWidget):
    """Depth stream + raw topic status for the :8082 raw-depth path."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        self._metric_labels: dict[str, QLabel] = {}
        self._source_kind = DepthSourceKind.OFFLINE
        self._stream_label = QLabel("深度流：未接入")
        self._source_label = QLabel("深度源：Offline")
        self._transport_label = QLabel("Raw depth transport: HTTP :8082")
        self._url_label = QLabel("Raw HTTP URL: -")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        title = QLabel("深度相机状态")
        title.setStyleSheet("font-weight: 600; color: #333;")
        root.addWidget(title)

        self._source_label.setStyleSheet("color: #444; font-size: 12px;")
        self._stream_label.setStyleSheet("color: #666; font-size: 12px;")
        self._transport_label.setStyleSheet("color: #666; font-size: 11px;")
        self._url_label.setStyleSheet("color: #666; font-size: 11px;")
        self._transport_label.setWordWrap(True)
        self._url_label.setWordWrap(True)
        root.addWidget(self._source_label)
        root.addWidget(self._stream_label)
        root.addWidget(self._transport_label)
        root.addWidget(self._url_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        rows = [
            ("depth_image", f"Raw topic: {CAMERA_DEPTH_IMAGE_TOPIC}"),
            ("depth_info", CAMERA_DEPTH_INFO_TOPIC),
            ("depth_points", CAMERA_DEPTH_POINTS_TOPIC),
        ]
        for row, (key, topic) in enumerate(rows):
            name = QLabel(topic + ":")
            name.setStyleSheet("color: #555; font-size: 11px;")
            value = QLabel("-")
            value.setStyleSheet("font-size: 11px;")
            self._labels[key] = value
            grid.addWidget(name, row, 0, Qt.AlignTop)
            grid.addWidget(value, row, 1)

        metric_rows = [
            ("fps", "深度 FPS:"),
            ("center", "中心距离:"),
            ("nearest", "最近有效:"),
            ("valid", "有效像素:"),
            ("range", "深度范围:"),
            ("latency", "延迟:"),
        ]
        base = len(rows)
        for offset, (key, label) in enumerate(metric_rows):
            name = QLabel(label)
            name.setStyleSheet("color: #555; font-size: 11px;")
            value = QLabel("-")
            value.setStyleSheet("font-size: 11px;")
            self._metric_labels[key] = value
            grid.addWidget(name, base + offset, 0, Qt.AlignTop)
            grid.addWidget(value, base + offset, 1)

        root.addLayout(grid)

    def set_http_info(self, url: str) -> None:
        self._transport_label.setText("Raw depth transport: HTTP :8082")
        self._url_label.setText(f"Raw HTTP URL: {url or '-'}")

    def set_stream_status(self, text: str) -> None:
        self._stream_label.setText(f"深度流：{text}")

    def set_source_kind(self, kind: DepthSourceKind | str) -> None:
        if isinstance(kind, str):
            try:
                kind = DepthSourceKind(kind)
            except ValueError:
                kind = DepthSourceKind.OFFLINE
        self._source_kind = kind
        labels = {
            DepthSourceKind.RAW_HTTP: "Raw HTTP :8082",
            DepthSourceKind.OFFLINE: "Offline",
        }
        self._source_label.setText(f"深度源：{labels.get(kind, str(kind))}")

    def apply_stats(self, stats: Optional[DepthFrameStats]) -> None:
        if stats is None:
            for lbl in self._metric_labels.values():
                lbl.setText("-")
            return
        self._metric_labels["fps"].setText(
            f"{stats.fps:.1f} Hz" if stats.fps > 0.01 else "-"
        )
        self._metric_labels["center"].setText(
            f"{stats.center_distance_m:.2f} m"
            if stats.center_distance_m > 0
            else "-"
        )
        self._metric_labels["nearest"].setText(
            f"{stats.nearest_valid_m:.2f} m"
            if stats.nearest_valid_m > 0
            else "-"
        )
        self._metric_labels["valid"].setText(
            f"{stats.valid_ratio * 100.0:.1f}%"
            if stats.valid_ratio > 0
            else "-"
        )
        if stats.min_depth_m > 0 and stats.max_depth_m > 0:
            self._metric_labels["range"].setText(
                f"{stats.min_depth_m:.2f} - {stats.max_depth_m:.2f} m"
            )
        else:
            self._metric_labels["range"].setText("-")
        self._metric_labels["latency"].setText(
            f"{stats.latency_ms:.0f} ms" if stats.latency_ms > 0 else "-"
        )
        info = self._labels.get("depth_info")
        if info is not None:
            info.setText("online" if stats.camera_info_online else "offline")

    def apply_probe(self, result: Optional[CameraTopicProbeResult]) -> None:
        if result is None:
            for lbl in self._labels.values():
                lbl.setText("-")
            return
        mapping = {
            "depth_image": CAMERA_DEPTH_IMAGE_TOPIC,
            "depth_info": CAMERA_DEPTH_INFO_TOPIC,
            "depth_points": CAMERA_DEPTH_POINTS_TOPIC,
        }
        for key, topic in mapping.items():
            entry = result.entries.get(topic)
            self._labels[key].setText(_format_entry(entry))


def _format_entry(entry: Optional[CameraTopicProbeEntry]) -> str:
    if entry is None:
        return "-"
    if entry.online:
        return f"online - {entry.detail}"
    return "offline"
