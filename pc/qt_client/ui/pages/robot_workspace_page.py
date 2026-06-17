from __future__ import annotations

from typing import Dict, Optional

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QRect, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from core import RobotSession
from ui.models.robot_info import RobotInfo
from ui.pages.placeholder_page import PlaceholderPage
from ui.widgets.robot_side_nav import CONTENT_PAGE_IDS, RobotSideNav

_WORKSPACE_PLACEHOLDERS: Dict[str, str] = {
    "overview": "总览功能待接入",
    "camera": "摄像头功能待接入",
    "robot": "机器人控制功能待接入",
    "slam_map": "SLAM 地图功能待接入",
    "gps_map": "GPS 地图功能待接入",
    "settings": "设置功能待接入",
    "about": "关于功能待接入",
}

_NAV_TITLES: Dict[str, str] = {
    "overview": "总览",
    "camera": "摄像头",
    "robot": "机器人",
    "slam_map": "SLAM 地图",
    "gps_map": "GPS 地图",
    "settings": "设置",
    "about": "关于",
}


class RobotWorkspacePage(QWidget):
    back_requested = pyqtSignal()

    def __init__(
        self,
        robot: RobotInfo,
        session: Optional[RobotSession] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.robot = robot
        self.session = session
        self._nav_open = False
        self._nav_width = 320
        self._nav_anim: Optional[QPropertyAnimation] = None
        self._side_nav = RobotSideNav()
        self._scrim = QWidget(self)
        self._stack = QStackedWidget()
        self._page_index: Dict[str, int] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        for page_id in CONTENT_PAGE_IDS:
            title = _NAV_TITLES.get(page_id, page_id)
            hint = _WORKSPACE_PLACEHOLDERS.get(page_id, "功能待接入")
            page = PlaceholderPage(title, hint)
            self._page_index[page_id] = self._stack.addWidget(page)
        root.addWidget(self._stack, 1)

        self._scrim.setStyleSheet("background: rgba(0, 0, 0, 0.45);")
        self._scrim.hide()
        self._scrim.mousePressEvent = self._on_scrim_pressed  # type: ignore[method-assign]

        self._side_nav.setParent(self)
        self._side_nav.page_selected.connect(self._on_nav_selected)
        self._side_nav.hide()

        self._show_content_page("overview")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_layer_geometry()

    def _nav_rect(self, opened: bool) -> QRect:
        x = 0 if opened else -self._nav_width
        return QRect(x, 0, self._nav_width, self.height())

    def _scrim_rect(self) -> QRect:
        return QRect(
            self._nav_width,
            0,
            max(0, self.width() - self._nav_width),
            self.height(),
        )

    def _sync_layer_geometry(self) -> None:
        self._scrim.setGeometry(self._scrim_rect())
        self._side_nav.setGeometry(self._nav_rect(opened=self._nav_open))

    def _on_scrim_pressed(self, event) -> None:
        self.close_navigation()
        event.accept()

    def toggle_navigation(self) -> None:
        if self._nav_open:
            self.close_navigation()
        else:
            self.open_navigation()

    def open_navigation(self) -> None:
        if self._nav_open:
            return
        self._nav_open = True
        self._sync_layer_geometry()
        self._scrim.show()
        self._side_nav.show()
        self._scrim.raise_()
        self._side_nav.raise_()
        self._animate_navigation(opened=True)

    def close_navigation(self) -> None:
        if not self._nav_open:
            return
        self._nav_open = False
        self._animate_navigation(opened=False)

    def _animate_navigation(self, opened: bool) -> None:
        if self._nav_anim is not None:
            self._nav_anim.stop()
        self._nav_anim = QPropertyAnimation(self._side_nav, b"geometry", self)
        self._nav_anim.setDuration(180)
        self._nav_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._nav_anim.setStartValue(self._side_nav.geometry())
        self._nav_anim.setEndValue(self._nav_rect(opened))
        if not opened:
            self._nav_anim.finished.connect(self._after_navigation_closed)
        self._nav_anim.start()

    def _after_navigation_closed(self) -> None:
        if self._nav_open:
            return
        self._side_nav.hide()
        self._scrim.hide()

    def _on_nav_selected(self, page_id: str) -> None:
        if page_id == "back":
            self.back_requested.emit()
            return
        self._show_content_page(page_id)
        self.close_navigation()

    def _show_content_page(self, page_id: str) -> None:
        index = self._page_index.get(page_id)
        if index is None:
            return
        self._stack.setCurrentIndex(index)
        self._side_nav.set_active(page_id)
