from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget

from ui.assets import android_asset


@dataclass(frozen=True)
class RobotNavItem:
    page_id: str
    title: str
    icon: str


ROBOT_WORKSPACE_NAV: List[RobotNavItem] = [
    RobotNavItem("back", "选择机器人", "ic_android_black_24dp.png"),
    RobotNavItem("overview", "总览", "ic_view_quilt_black_24dp.png"),
    RobotNavItem("camera", "摄像头", "ic_linked_camera_black_24dp.png"),
    RobotNavItem("robot", "2D 雷达", "ic_navigation_black_24dp.png"),
    RobotNavItem("odom_compare", "里程计对照", "ic_action_topics.png"),
    RobotNavItem("slam_map", "SLAM 地图", "ic_terrain_black_24dp.png"),
    RobotNavItem("gps_map", "GPS 地图", "ic_flag_black_24dp.png"),
    RobotNavItem("settings", "设置", "ic_settings_black_24dp.png"),
    RobotNavItem("about", "关于", "ic_info_outline_black_24dp.png"),
]

CONTENT_PAGE_IDS: Tuple[str, ...] = tuple(
    item.page_id for item in ROBOT_WORKSPACE_NAV if item.page_id != "back"
)


class RobotSideNav(QWidget):
    page_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: Dict[str, QPushButton] = {}
        self._active_id = "overview"
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedWidth(320)
        # RobotSideNav is a custom QWidget.  Force its styled background to
        # paint across the stretch area below the last button; otherwise the
        # underlying page controls can show through there on some Qt styles.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "RobotSideNav { background-color: #ffffff; "
            "border-right: 1px solid #ddd; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        for item in ROBOT_WORKSPACE_NAV:
            btn = QPushButton(f"  {item.title}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(64)
            btn.setIcon(QIcon(android_asset(item.icon)))
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(self._button_style(active=False))
            btn.clicked.connect(
                lambda _=False, pid=item.page_id: self.page_selected.emit(pid)
            )
            root.addWidget(btn)
            self._buttons[item.page_id] = btn

        root.addStretch(1)
        self.set_active("overview")

    def _button_style(self, active: bool) -> str:
        background = "background:#efefef;" if active else ""
        return (
            "QPushButton{ text-align:left; padding-left: 18px; border:none; "
            f"{background} font-size: 15px; }}"
            "QPushButton:hover{ background:#f3f3f3; }"
        )

    def set_active(self, page_id: str) -> None:
        if page_id == "back":
            return
        self._active_id = page_id
        for pid, btn in self._buttons.items():
            btn.setStyleSheet(self._button_style(active=pid == page_id and pid != "back"))
