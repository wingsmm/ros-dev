from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    def __init__(self, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._hint = hint
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(10)

        title = QLabel(self._title)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        hint = QLabel(self._hint or "功能待接入")
        hint.setStyleSheet("color: #666;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        sub = QLabel("当前阶段只完成页面切换壳，具体功能后续接入。")
        sub.setStyleSheet("color: #888; font-size: 12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        root.addStretch(1)
