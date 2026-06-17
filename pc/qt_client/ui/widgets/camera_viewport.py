from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class CameraViewport(QWidget):
    """Image display only: empty / loading / streaming / stalled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "empty"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("暂无摄像头画面")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMinimumHeight(280)
        self._label.setStyleSheet(
            "QLabel { background: #111; color: #aaa; border: 1px solid #333;"
            " font-size: 15px; }"
        )
        self._label.setScaledContents(False)
        root.addWidget(self._label, 1)

    def set_loading(self, message: str = "正在连接...") -> None:
        self._state = "loading"
        self._label.setPixmap(QPixmap())
        self._label.setText(message)

    def set_empty(self, message: str = "暂无摄像头画面") -> None:
        self._state = "empty"
        self._label.setPixmap(QPixmap())
        self._label.setText(message)

    def set_stalled(self, message: str = "画面中断") -> None:
        self._state = "stalled"
        self._label.setPixmap(QPixmap())
        self._label.setText(message)

    def set_frame_jpeg(self, jpeg: bytes) -> None:
        img = QImage.fromData(jpeg)
        if img.isNull():
            return
        self._state = "streaming"
        pix = QPixmap.fromImage(img)
        target = self._label.size()
        if target.width() > 10 and target.height() > 10:
            pix = pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label.setPixmap(pix)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        pix = self._label.pixmap()
        if pix is None or pix.isNull() or self._state != "streaming":
            return
        target = self._label.size()
        if target.width() > 10 and target.height() > 10:
            self._label.setPixmap(
                pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
