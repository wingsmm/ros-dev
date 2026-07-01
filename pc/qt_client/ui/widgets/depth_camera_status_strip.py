"""One-line depth page status: raw HTTP / CameraInfo / PointCloud / RViz."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget


class DepthCameraStatusStrip(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._label = QLabel("Depth raw HTTP: — | CameraInfo: — | PointCloud2: — | RViz: —")
        self._label.setStyleSheet("color: #444; font-size: 12px;")
        self._label.setWordWrap(True)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.addWidget(self._label, 1)

    def set_status(
        self,
        *,
        raw_http: str,
        camera_info: str,
        pointcloud: str,
        rviz: str,
    ) -> None:
        self._label.setText(
            f"Depth raw HTTP: {raw_http} | CameraInfo: {camera_info} | "
            f"PointCloud2: {pointcloud} | RViz: {rviz}"
        )
