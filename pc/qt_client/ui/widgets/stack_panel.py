from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class StackPanel(QGroupBox):
    start_rviz = pyqtSignal()
    stop_rviz = pyqtSignal()
    start_slam = pyqtSignal()
    stop_slam = pyqtSignal()
    start_all = pyqtSignal()
    stop_all = pyqtSignal()

    def __init__(self) -> None:
        super().__init__("建图栈")
        root = QVBoxLayout(self)

        hint = QLabel("RViz2 / SLAM 由此窗口启动，无需另开终端。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.ros2_hint = QLabel("")
        self.ros2_hint.setWordWrap(True)
        root.addWidget(self.ros2_hint)

        row_rviz = QHBoxLayout()
        self.rviz_status = QLabel("RViz2: 未运行")
        self.rviz_start_btn = QPushButton("启动 RViz2")
        self.rviz_stop_btn = QPushButton("停止")
        self.rviz_stop_btn.setEnabled(False)
        row_rviz.addWidget(self.rviz_status, 1)
        row_rviz.addWidget(self.rviz_start_btn)
        row_rviz.addWidget(self.rviz_stop_btn)
        root.addLayout(row_rviz)

        row_slam = QHBoxLayout()
        self.slam_status = QLabel("SLAM: 未运行")
        self.slam_start_btn = QPushButton("启动 SLAM")
        self.slam_stop_btn = QPushButton("停止")
        self.slam_stop_btn.setEnabled(False)
        row_slam.addWidget(self.slam_status, 1)
        row_slam.addWidget(self.slam_start_btn)
        row_slam.addWidget(self.slam_stop_btn)
        root.addLayout(row_slam)

        row_all = QHBoxLayout()
        self.all_start_btn = QPushButton("一键启动建图栈")
        self.all_stop_btn = QPushButton("全部停止")
        row_all.addWidget(self.all_start_btn)
        row_all.addWidget(self.all_stop_btn)
        row_all.addStretch(1)
        root.addLayout(row_all)

        self.rviz_start_btn.clicked.connect(self.start_rviz.emit)
        self.rviz_stop_btn.clicked.connect(self.stop_rviz.emit)
        self.slam_start_btn.clicked.connect(self.start_slam.emit)
        self.slam_stop_btn.clicked.connect(self.stop_slam.emit)
        self.all_start_btn.clicked.connect(self.start_all.emit)
        self.all_stop_btn.clicked.connect(self.stop_all.emit)

    def set_ros2_status(self, ok: bool, detail: str = "") -> None:
        if ok:
            self.ros2_hint.setText("ROS2 发布: 正常 (/odom_base + TF)")
            self.ros2_hint.setStyleSheet("color: green;")
        elif detail:
            self.ros2_hint.setText("ROS2 发布: " + detail)
            self.ros2_hint.setStyleSheet("color: darkorange;")
        else:
            self.ros2_hint.setText("ROS2 发布: 未启用")
            self.ros2_hint.setStyleSheet("color: gray;")

    def set_rviz_running(self, running: bool) -> None:
        self.rviz_status.setText("RViz2: 运行中" if running else "RViz2: 未运行")
        self.rviz_start_btn.setEnabled(not running)
        self.rviz_stop_btn.setEnabled(running)

    def set_slam_running(self, running: bool) -> None:
        self.slam_status.setText("SLAM: 运行中" if running else "SLAM: 未运行")
        self.slam_start_btn.setEnabled(not running)
        self.slam_stop_btn.setEnabled(running)
