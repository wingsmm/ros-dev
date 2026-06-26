from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QWidget


class CameraViewModeBar(QWidget):
    """RGB / Depth / split view selector for camera module."""

    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = "rgb"
        self._buttons: dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(6)
        for mode, label in (
            ("rgb", "RGB"),
            ("depth", "Depth"),
            ("split", "分屏"),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, m=mode: self._on_mode(m))
            self._buttons[mode] = btn
            root.addWidget(btn)
        root.addStretch(1)
        self._buttons["rgb"].setChecked(True)
        self._style_active("rgb")

    def _on_mode(self, mode: str) -> None:
        if self._mode == mode:
            self._buttons[mode].setChecked(True)
            return
        self._mode = mode
        self._style_active(mode)
        self.mode_changed.emit(mode)

    def _style_active(self, mode: str) -> None:
        for key, btn in self._buttons.items():
            active = key == mode
            btn.setChecked(active)
            btn.setStyleSheet(
                "font-weight: 600;" if active else ""
            )

    def current_mode(self) -> str:
        return self._mode
