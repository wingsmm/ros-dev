from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.models import RobotInfo


class RobotDeletePage(QWidget):
    delete_confirmed = pyqtSignal(str)
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._robot_id: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("删除机器人")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        self._hint_label = QLabel("确认删除以下机器人？")
        self._hint_label.setWordWrap(True)
        root.addWidget(self._hint_label)

        self._name_label = QLabel()
        self._name_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        root.addWidget(self._name_label)

        self._uri_label = QLabel()
        self._uri_label.setStyleSheet("color: #666;")
        self._uri_label.setWordWrap(True)
        root.addWidget(self._uri_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        btn_row.addWidget(self.cancel_btn)
        self.confirm_btn = QPushButton("确认删除")
        self.confirm_btn.setStyleSheet(
            "QPushButton { background: #c62828; color: white; padding: 8px 16px; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #b71c1c; }"
        )
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)
        root.addLayout(btn_row)
        root.addStretch(1)

    def prepare(self, robot: RobotInfo) -> None:
        self._robot_id = robot.id
        self._name_label.setText(robot.name)
        self._uri_label.setText(robot.master_uri)

    def _on_confirm(self) -> None:
        if self._robot_id:
            self.delete_confirmed.emit(self._robot_id)
