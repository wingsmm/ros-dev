from __future__ import annotations

from typing import Callable, List, Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.assets import android_asset
from ui.models import RobotInfo


class _RobotCard(QFrame):
    selected = pyqtSignal(str)
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, robot: RobotInfo, parent=None):
        super().__init__(parent)
        self._robot_id = robot.id
        self._build_ui(robot)

    def _build_ui(self, robot: RobotInfo) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #fff; border: 1px solid #e2e2e2; border-radius: 8px; }"
        )
        self.setMinimumHeight(86)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)

        body = QWidget()
        body.setCursor(Qt.PointingHandCursor)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        name = QLabel(robot.name)
        name.setStyleSheet("font-size: 15px; font-weight: 600;")
        uri = QLabel(robot.master_uri)
        uri.setStyleSheet("color: #666; font-size: 12px;")
        body_layout.addWidget(name)
        body_layout.addWidget(uri)
        body_layout.addStretch(1)

        def select_robot(event) -> None:
            self.selected.emit(self._robot_id)
            event.accept()

        body.mousePressEvent = select_robot  # type: ignore[method-assign]
        row.addWidget(body, 1)

        btn_wifi = self._icon_button("wifi_0.png", "连接状态（占位）")
        btn_wifi.setEnabled(False)
        btn_edit = self._icon_button(
            "ic_edit_black_24dp.png",
            "编辑",
            lambda: self.edit_requested.emit(self._robot_id),
        )
        btn_del = self._icon_button(
            "ic_delete_black_24dp.png",
            "删除",
            lambda: self.delete_requested.emit(self._robot_id),
        )
        for b in (btn_wifi, btn_edit, btn_del):
            row.addWidget(b)

    def _icon_button(
        self,
        asset: str,
        tooltip: str,
        on_click: Optional[Callable[[], None]] = None,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(34, 34)
        btn.setIconSize(QSize(22, 22))
        btn.setIcon(QIcon(android_asset(asset)))
        btn.setToolTip(tooltip)
        btn.setStyleSheet(
            "QPushButton { background:#f5f5f5; border:1px solid #ddd; border-radius:6px; }"
            "QPushButton:hover { background:#eee; }"
            "QPushButton:disabled { background:#fafafa; }"
        )
        if on_click is not None:
            btn.clicked.connect(on_click)
        return btn


class RobotListPage(QWidget):
    robot_selected = pyqtSignal(str)
    robot_edit_requested = pyqtSignal(str)
    robot_delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards_layout: Optional[QVBoxLayout] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("机器人遥控")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        list_host = QWidget()
        self._cards_layout = QVBoxLayout(list_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)
        self._cards_layout.addStretch(1)
        scroll.setWidget(list_host)
        root.addWidget(scroll, 1)

    def set_robots(self, robots: List[RobotInfo]) -> None:
        if self._cards_layout is None:
            return
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for robot in robots:
            card = _RobotCard(robot)
            card.selected.connect(self.robot_selected.emit)
            card.edit_requested.connect(self.robot_edit_requested.emit)
            card.delete_requested.connect(self.robot_delete_requested.emit)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
