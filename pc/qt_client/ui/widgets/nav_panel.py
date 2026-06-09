from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class NavPanel(QGroupBox):
    start_localization = pyqtSignal()
    stop_localization = pyqtSignal()
    start_navigation = pyqtSignal()
    stop_navigation = pyqtSignal()
    start_nav_all = pyqtSignal()
    stop_nav_all = pyqtSignal()
    emergency_stop = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("导航栈")
        root = QVBoxLayout(self)

        hint = QLabel(
            "使用已存地图（maps/*.yaml）。导航运行时禁用手动遥控，"
            "在 RViz2 用「2D Goal Pose」设目标点。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        row_map = QHBoxLayout()
        row_map.addWidget(QLabel("地图 yaml"))
        self.map_yaml_edit = QLineEdit()
        self.map_yaml_edit.setPlaceholderText("maps/xtark_xxx.yaml（相对 qt_client）")
        row_map.addWidget(self.map_yaml_edit, 1)
        root.addLayout(row_map)

        row_loc = QHBoxLayout()
        self.loc_status = QLabel("定位: 未运行")
        self.loc_start_btn = QPushButton("启动定位")
        self.loc_stop_btn = QPushButton("停止")
        self.loc_stop_btn.setEnabled(False)
        row_loc.addWidget(self.loc_status, 1)
        row_loc.addWidget(self.loc_start_btn)
        row_loc.addWidget(self.loc_stop_btn)
        root.addLayout(row_loc)

        row_nav = QHBoxLayout()
        self.nav_status = QLabel("Nav2: 未运行")
        self.nav_start_btn = QPushButton("启动 Nav2")
        self.nav_stop_btn = QPushButton("停止")
        self.nav_stop_btn.setEnabled(False)
        row_nav.addWidget(self.nav_status, 1)
        row_nav.addWidget(self.nav_start_btn)
        row_nav.addWidget(self.nav_stop_btn)
        root.addLayout(row_nav)

        row_all = QHBoxLayout()
        self.nav_all_start_btn = QPushButton("一键启动导航栈")
        self.nav_all_stop_btn = QPushButton("停止导航栈")
        self.estop_btn = QPushButton("急停")
        self.estop_btn.setStyleSheet("font-weight: bold;")
        row_all.addWidget(self.nav_all_start_btn)
        row_all.addWidget(self.nav_all_stop_btn)
        row_all.addWidget(self.estop_btn)
        row_all.addStretch(1)
        root.addLayout(row_all)

        self.loc_start_btn.clicked.connect(self.start_localization.emit)
        self.loc_stop_btn.clicked.connect(self.stop_localization.emit)
        self.nav_start_btn.clicked.connect(self.start_navigation.emit)
        self.nav_stop_btn.clicked.connect(self.stop_navigation.emit)
        self.nav_all_start_btn.clicked.connect(self.start_nav_all.emit)
        self.nav_all_stop_btn.clicked.connect(self.stop_nav_all.emit)
        self.estop_btn.clicked.connect(self.emergency_stop.emit)

    def map_yaml(self) -> str:
        return self.map_yaml_edit.text().strip()

    def set_map_yaml(self, path: str) -> None:
        self.map_yaml_edit.setText(path)

    def set_localization_running(self, running: bool) -> None:
        self.loc_status.setText("定位: 运行中" if running else "定位: 未运行")
        self.loc_start_btn.setEnabled(not running)
        self.loc_stop_btn.setEnabled(running)

    def set_navigation_running(self, running: bool) -> None:
        self.nav_status.setText("Nav2: 运行中" if running else "Nav2: 未运行")
        self.nav_start_btn.setEnabled(not running)
        self.nav_stop_btn.setEnabled(running)

    def set_nav_active(self, active: bool) -> None:
        """Nav stack engaged: disable manual teleop in parent."""
        self.nav_all_start_btn.setEnabled(not active)
        self.nav_all_stop_btn.setEnabled(active)
