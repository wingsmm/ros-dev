from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class CameraToolbar(QWidget):
    """MJPEG stream URLs (read-only) + connect controls + status/FPS display."""

    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()
    reconnect_requested = pyqtSignal()
    snapshot_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(6)

        btn_row = QHBoxLayout()
        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.reconnect_btn = QPushButton("重连")
        self.snapshot_btn = QPushButton("截图")
        self.disconnect_btn.setEnabled(False)
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addWidget(self.reconnect_btn)
        btn_row.addWidget(self.snapshot_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        url_grid = QGridLayout()
        url_grid.setHorizontalSpacing(8)
        url_grid.setVerticalSpacing(4)
        readonly_style = "QLineEdit { background: #f5f5f5; color: #333; }"

        rgb_caption = QLabel("RGB MJPEG")
        rgb_caption.setStyleSheet("color: #555; font-size: 12px;")
        self.rgb_url_edit = QLineEdit()
        self.rgb_url_edit.setReadOnly(True)
        self.rgb_url_edit.setFocusPolicy(Qt.StrongFocus)
        self.rgb_url_edit.setPlaceholderText("http://host:8080/stream?topic=/camera/image_raw")
        self.rgb_url_edit.setStyleSheet(readonly_style)
        url_grid.addWidget(rgb_caption, 0, 0, Qt.AlignTop)
        url_grid.addWidget(self.rgb_url_edit, 0, 1)

        depth_caption = QLabel("Depth raw HTTP")
        depth_caption.setStyleSheet("color: #555; font-size: 12px;")
        self.depth_url_edit = QLineEdit()
        self.depth_url_edit.setReadOnly(True)
        self.depth_url_edit.setFocusPolicy(Qt.StrongFocus)
        self.depth_url_edit.setPlaceholderText("http://host:8082/v1/depth/latest")
        self.depth_url_edit.setStyleSheet(readonly_style)
        url_grid.addWidget(depth_caption, 1, 0, Qt.AlignTop)
        url_grid.addWidget(self.depth_url_edit, 1, 1)

        url_grid.setColumnStretch(1, 1)
        root.addLayout(url_grid)

        hint = QLabel("由 robots.json / master_uri 自动生成，不可编辑")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(hint)

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
        self.snapshot_btn.clicked.connect(self.snapshot_requested.emit)

    def set_stream_urls(self, rgb_url: str, depth_url: str) -> None:
        self.rgb_url_edit.setText(rgb_url)
        self.depth_url_edit.setText(depth_url)

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

    def set_snapshot_visible(self, visible: bool) -> None:
        self.snapshot_btn.setVisible(visible)
        self.snapshot_btn.setEnabled(visible)

    def set_connecting(self) -> None:
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(False)
