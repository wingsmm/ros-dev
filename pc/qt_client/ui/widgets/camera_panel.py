from __future__ import annotations

import time

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.mjpeg_stream import MjpegStreamController


class CameraPanel(QWidget):
    log = pyqtSignal(str)

    def __init__(
        self,
        settings_key: str = "camera_http_url",
        default_url: str = "http://192.168.1.168:8080/stream?topic=/camera/image_raw",
        parent=None,
    ):
        super().__init__(parent)
        self._settings_key = settings_key
        self._default_url = default_url
        self._stream = MjpegStreamController(self)
        self._last_ui_frame_ts = 0.0
        self._build_ui()
        self._wire_stream()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        group = QGroupBox("相机（HTTP/MJPEG）")
        g = QVBoxLayout(group)

        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(self._default_url)
        row.addWidget(QLabel("URL"))
        row.addWidget(self.url_edit, 1)
        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.reconnect_btn = QPushButton("重连")
        self.disconnect_btn.setEnabled(False)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        row.addWidget(self.reconnect_btn)
        g.addLayout(row)

        self.image_label = QLabel("No Camera")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(200)
        self.image_label.setStyleSheet(
            "QLabel { background: #111; color: #ddd; border: 1px solid #333; }"
        )
        self.image_label.setScaledContents(False)
        g.addWidget(self.image_label, 1)

        info_row = QHBoxLayout()
        self.status_label = QLabel("No Camera")
        self.fps_label = QLabel("FPS: -")
        info_row.addWidget(self.status_label, 1)
        info_row.addWidget(self.fps_label, 0, Qt.AlignRight)
        g.addLayout(info_row)

        root.addWidget(group)

        self.connect_btn.clicked.connect(self.connect)
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.reconnect_btn.clicked.connect(self.reconnect)

    def _wire_stream(self) -> None:
        self._stream.frame.connect(self._on_frame)
        self._stream.status_changed.connect(self._on_status)
        self._stream.connected_changed.connect(self._on_connected)
        self._stream.fps_changed.connect(self._on_fps)
        self._stream.log_line.connect(self.log.emit)

    def set_url(self, url: str) -> None:
        self.url_edit.setText(url)

    def url(self) -> str:
        text = self.url_edit.text().strip()
        return text or self._default_url

    def connect(self) -> None:
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.reconnect_btn.setEnabled(True)
        self._stream.connect(self.url())

    def disconnect(self, block: bool = False) -> None:
        self._stream.disconnect(block=block)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

    def reconnect(self) -> None:
        self._stream.reconnect(self.url())

    def shutdown(self) -> None:
        self._stream.shutdown()

    def load_settings(self, settings) -> None:
        url = str(settings.value(self._settings_key, self._default_url))
        self.set_url(url)

    def save_settings(self, settings) -> None:
        settings.setValue(self._settings_key, self.url())

    def _on_status(self, text: str) -> None:
        self.status_label.setText(text)
        if not self._stream.stats.connected:
            if self._stream.stats.last_frame_ts <= 0:
                self.image_label.setPixmap(QPixmap())
                self.image_label.setText("No Camera")

    def _on_connected(self, ok: bool) -> None:
        self.connect_btn.setEnabled(not ok)
        self.disconnect_btn.setEnabled(ok)
        if not ok and self._stream.stats.last_frame_ts <= 0:
            self.image_label.setText("No Camera")

    def _on_fps(self, fps: float) -> None:
        if fps <= 0:
            self.fps_label.setText("FPS: -")
        else:
            self.fps_label.setText("FPS: {:.1f}".format(fps))
        if self._stream.stats.last_frame_ts > 0:
            if time.time() - self._stream.stats.last_frame_ts > 2.0:
                self.image_label.setPixmap(QPixmap())
                self.image_label.setText("No Camera")
                self.status_label.setText("No frames (timeout)")
                self.fps_label.setText("FPS: 0.0")

    def _on_frame(self, jpeg: bytes) -> None:
        from PyQt5.QtGui import QImage

        img = QImage.fromData(jpeg)
        if img.isNull():
            return
        self._last_ui_frame_ts = time.time()
        pix = QPixmap.fromImage(img)
        target = self.image_label.size()
        if target.width() > 10 and target.height() > 10:
            pix = pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)
        self.status_label.setText("OK")
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
