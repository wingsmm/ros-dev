from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

_VIEW_RGB = "rgb"
_VIEW_DEPTH = "depth"
_VIEW_SPLIT = "split"


class CameraViewport(QWidget):
    """RGB / Depth / split preview. Depth may show placeholder when no stream."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = _VIEW_RGB
        self._rgb_state = "empty"
        self._depth_state = "empty"
        self._rgb_pix: Optional[QPixmap] = None
        self._depth_pix: Optional[QPixmap] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._single_label = QLabel("暂无摄像头画面")
        self._single_label.setAlignment(Qt.AlignCenter)
        self._single_label.setMinimumHeight(280)
        self._single_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._single_label.setStyleSheet(self._label_style())
        self._single_label.setScaledContents(False)

        split = QHBoxLayout()
        split.setSpacing(4)
        self._rgb_label = QLabel("RGB")
        self._depth_label = QLabel("深度未接入")
        for lbl in (self._rgb_label, self._depth_label):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumHeight(240)
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            lbl.setStyleSheet(self._label_style())
            lbl.setScaledContents(False)
        split.addWidget(self._rgb_label, 1)
        split.addWidget(self._depth_label, 1)

        self._split_wrap = QWidget()
        self._split_wrap.setLayout(split)
        self._split_wrap.setVisible(False)

        root.addWidget(self._single_label, 1)
        root.addWidget(self._split_wrap, 1)

    @staticmethod
    def _label_style() -> str:
        return (
            "QLabel { background: #111; color: #aaa; border: 1px solid #333;"
            " font-size: 14px; }"
        )

    def set_view_mode(self, mode: str) -> None:
        # 感知模式使用单视图显示（与 RGB 模式相同的 UI）
        if mode == "perception":
            mode = _VIEW_RGB
        mode = mode if mode in (_VIEW_RGB, _VIEW_DEPTH, _VIEW_SPLIT) else _VIEW_RGB
        if self._mode == mode:
            return
        self._mode = mode
        self._split_wrap.setVisible(mode == _VIEW_SPLIT)
        self._single_label.setVisible(mode != _VIEW_SPLIT)
        self._refresh_visible()

    def _active_single_label(self) -> QLabel:
        return self._single_label

    def _refresh_visible(self) -> None:
        if self._mode == _VIEW_SPLIT:
            return
        if self._mode == _VIEW_RGB:
            self._apply_state_to_label(self._single_label, self._rgb_state, "rgb")
        else:
            self._apply_state_to_label(
                self._single_label, self._depth_state, "depth"
            )

    def _apply_state_to_label(
        self, label: QLabel, state: str, kind: str
    ) -> None:
        if state == "streaming":
            return
        label.setPixmap(QPixmap())
        if state == "loading":
            label.setText("正在连接...")
        elif state == "stalled":
            label.setText("画面中断")
        elif kind == "depth":
            label.setText("深度相机未接入 / 无深度流")
        else:
            label.setText("暂无摄像头画面")

    def set_loading(self, message: str = "正在连接...") -> None:
        self._rgb_state = "loading"
        if self._mode == _VIEW_RGB:
            self._single_label.setPixmap(QPixmap())
            self._single_label.setText(message)
        elif self._mode == _VIEW_SPLIT:
            self._rgb_label.setPixmap(QPixmap())
            self._rgb_label.setText(message)
        else:
            self._depth_state = "loading"
            self._single_label.setPixmap(QPixmap())
            self._single_label.setText(message)

    def set_empty(self, message: str = "暂无摄像头画面") -> None:
        self._rgb_state = "empty"
        if self._mode == _VIEW_RGB:
            self._single_label.setPixmap(QPixmap())
            self._single_label.setText(message)
        elif self._mode == _VIEW_SPLIT:
            self._rgb_label.setPixmap(QPixmap())
            self._rgb_label.setText(message)

    def set_stalled(self, message: str = "画面中断") -> None:
        self._rgb_state = "stalled"
        if self._mode in (_VIEW_RGB, _VIEW_SPLIT):
            target = self._rgb_label if self._mode == _VIEW_SPLIT else self._single_label
            target.setPixmap(QPixmap())
            target.setText(message)

    def set_depth_loading(self, message: str = "正在连接深度流...") -> None:
        self._depth_state = "loading"
        if self._mode == _VIEW_DEPTH:
            self._single_label.setPixmap(QPixmap())
            self._single_label.setText(message)
        elif self._mode == _VIEW_SPLIT:
            self._depth_label.setPixmap(QPixmap())
            self._depth_label.setText(message)

    def set_depth_empty(
        self, message: str = "深度相机未接入 / 无深度流"
    ) -> None:
        self._depth_state = "empty"
        if self._mode == _VIEW_DEPTH:
            self._single_label.setPixmap(QPixmap())
            self._single_label.setText(message)
        elif self._mode == _VIEW_SPLIT:
            self._depth_label.setPixmap(QPixmap())
            self._depth_label.setText(message)

    def set_depth_stalled(self, message: str = "深度画面中断") -> None:
        self._depth_state = "stalled"
        if self._mode == _VIEW_DEPTH:
            self._single_label.setPixmap(QPixmap())
            self._single_label.setText(message)
        elif self._mode == _VIEW_SPLIT:
            self._depth_label.setPixmap(QPixmap())
            self._depth_label.setText(message)

    def set_frame_jpeg(self, jpeg: bytes) -> None:
        if self._mode == _VIEW_DEPTH:
            return
        self._show_jpeg(jpeg, kind="rgb")

    def set_frame_rgb(self, image: QImage) -> None:
        """直接设置 RGB QImage（用于感知模式的 Overlay）"""
        if self._mode == _VIEW_DEPTH:
            return
        if image.isNull():
            return
        self._show_pixmap(QPixmap.fromImage(image), kind="rgb")

    def set_depth_frame_jpeg(self, jpeg: bytes) -> None:
        if self._mode == _VIEW_RGB:
            return
        self._show_jpeg(jpeg, kind="depth")

    def set_depth_frame_rgb(
        self, width: int, height: int, rgb_bytes: bytes
    ) -> None:
        if self._mode == _VIEW_RGB:
            return
        if not rgb_bytes or width <= 0 or height <= 0:
            return
        if len(rgb_bytes) != width * height * 3:
            return
        img = QImage(
            rgb_bytes, width, height, width * 3, QImage.Format_RGB888
        ).copy()
        if img.isNull():
            return
        self._show_pixmap(QPixmap.fromImage(img), kind="depth")

    def _show_jpeg(self, jpeg: bytes, *, kind: str) -> None:
        img = QImage.fromData(jpeg)
        if img.isNull():
            return
        self._show_pixmap(QPixmap.fromImage(img), kind=kind)

    def _show_pixmap(self, pix: QPixmap, *, kind: str) -> None:
        if kind == "rgb":
            self._rgb_pix = pix
            self._rgb_state = "streaming"
            if self._mode == _VIEW_SPLIT:
                target = self._rgb_label
            elif self._mode == _VIEW_RGB:
                target = self._single_label
            else:
                return
        else:
            self._depth_pix = pix
            self._depth_state = "streaming"
            if self._mode == _VIEW_SPLIT:
                target = self._depth_label
            elif self._mode == _VIEW_DEPTH:
                target = self._single_label
            else:
                return
        self._scale_pixmap(target, pix)

    def _scale_pixmap(self, label: QLabel, pix: QPixmap) -> QLabel:
        target = label.size()
        if target.width() > 10 and target.height() > 10:
            label.setPixmap(
                pix.scaled(target, Qt.KeepAspectRatio, Qt.FastTransformation)
            )
        else:
            label.setPixmap(pix)
        return label

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for label, kind in (
            (
                self._single_label,
                "rgb" if self._mode == _VIEW_RGB else "depth",
            ),
            (self._rgb_label, "rgb"),
            (self._depth_label, "depth"),
        ):
            if not label.isVisible():
                continue
            state = self._rgb_state if kind == "rgb" else self._depth_state
            if state != "streaming":
                continue
            src = self._rgb_pix if kind == "rgb" else self._depth_pix
            if src is not None and not src.isNull():
                self._scale_pixmap(label, src)
