from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class CameraToolbar(QWidget):
    """MJPEG URL + connect controls + status/FPS display."""

    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()
    reconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(6)

        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("http://host:8080/stream?topic=/camera/image_raw")
        row.addWidget(QLabel("URL"))
        row.addWidget(self.url_edit, 1)

        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.reconnect_btn = QPushButton("重连")
        self.disconnect_btn.setEnabled(False)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        row.addWidget(self.reconnect_btn)
        root.addLayout(row)

        info = QHBoxLayout()
        self.topic_label = QLabel("话题: --")
        self.status_label = QLabel("No Camera")
        self.fps_label = QLabel("FPS: -")
        self.topic_label.setStyleSheet("color: #666; font-size: 12px;")
        info.addWidget(self.topic_label)
        info.addWidget(self.status_label, 1)
        info.addWidget(self.fps_label, 0)
        root.addLayout(info)

        self.connect_btn.clicked.connect(self.connect_requested.emit)
        self.disconnect_btn.clicked.connect(self.disconnect_requested.emit)
        self.reconnect_btn.clicked.connect(self.reconnect_requested.emit)

    def set_url(self, url: str) -> None:
        self.url_edit.setText(url)

    def url(self) -> str:
        return self.url_edit.text().strip()

    def set_topic_hint(self, topic: str) -> None:
        self.topic_label.setText(f"话题: {topic}")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_fps(self, fps: float) -> None:
        if fps <= 0:
            self.fps_label.setText("FPS: -")
        else:
            self.fps_label.setText(f"FPS: {fps:.1f}")

    def set_streaming(self, streaming: bool) -> None:
        self.connect_btn.setEnabled(not streaming)
        self.disconnect_btn.setEnabled(streaming)
        self.reconnect_btn.setEnabled(True)

    def set_connecting(self) -> None:
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(False)
