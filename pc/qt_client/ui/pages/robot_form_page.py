from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.models import RobotInfo


class RobotFormPage(QWidget):
    save_requested = pyqtSignal(object)  # RobotInfo
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "add"
        self._robot_id: Optional[str] = None
        self._original_robot: Optional[RobotInfo] = None
        self._layout_ready = False
        self._build_ui()
        self._layout_ready = True

    def _build_ui(self) -> None:
        self.setMinimumWidth(720)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)

        self._title_label = QLabel("添加/编辑机器人")
        self._title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(self._title_label)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("机器人名称")
        self.uri_edit = QLineEdit()
        self.uri_edit.setPlaceholderText("http://192.168.1.169:11311")
        self._configure_line_edit(self.name_edit)
        self._configure_line_edit(self.uri_edit)
        form.addRow("机器人名称", self.name_edit)
        form.addRow("Master URI", self.uri_edit)
        root.addLayout(form)

        self.advanced_checkbox = QCheckBox("显示高级选项")
        self.advanced_checkbox.toggled.connect(self._set_advanced_visible)
        root.addWidget(self.advanced_checkbox)

        self.advanced_widget = QWidget()
        advanced_form = QFormLayout(self.advanced_widget)
        advanced_form.setSpacing(12)
        advanced_form.setLabelAlignment(Qt.AlignRight)

        self.joystick_edit = QLineEdit()
        self.laser_edit = QLineEdit()
        self.camera_edit = QLineEdit()
        self.navsat_edit = QLineEdit()
        self.odometry_edit = QLineEdit()
        self.pose_edit = QLineEdit()
        self.reverse_laser_checkbox = QCheckBox()
        self.invert_x_checkbox = QCheckBox()
        self.invert_y_checkbox = QCheckBox()
        self.invert_angular_checkbox = QCheckBox()
        for edit in (
            self.joystick_edit,
            self.laser_edit,
            self.camera_edit,
            self.navsat_edit,
            self.odometry_edit,
            self.pose_edit,
        ):
            self._configure_line_edit(edit)

        advanced_form.addRow("摇杆话题", self.joystick_edit)
        advanced_form.addRow("激光扫描话题", self.laser_edit)
        advanced_form.addRow("摄像头话题", self.camera_edit)
        advanced_form.addRow("GPS 话题", self.navsat_edit)
        advanced_form.addRow("里程计话题", self.odometry_edit)
        advanced_form.addRow("位姿话题", self.pose_edit)
        advanced_form.addRow("反转激光扫描", self.reverse_laser_checkbox)
        advanced_form.addRow("反转 X 轴", self.invert_x_checkbox)
        advanced_form.addRow("反转 Y 轴", self.invert_y_checkbox)
        advanced_form.addRow("反转角速度", self.invert_angular_checkbox)
        root.addWidget(self.advanced_widget)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 8, 0, 0)
        btn_row.setSpacing(16)
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumWidth(96)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        btn_row.addWidget(self.cancel_btn)
        self.save_btn = QPushButton("确定")
        self.save_btn.setMinimumWidth(96)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)
        self._set_advanced_visible(False)

    def _configure_line_edit(self, edit: QLineEdit) -> None:
        edit.setMinimumWidth(500)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def prepare_add(self) -> None:
        self._mode = "add"
        self._robot_id = None
        self._original_robot = None
        self._title_label.setText("添加/编辑机器人")
        self._load_robot(RobotInfo(id=RobotInfo.new_id(), name="", master_uri=""))
        self.advanced_checkbox.setChecked(False)
        self.name_edit.setFocus()

    def prepare_edit(self, robot: RobotInfo) -> None:
        self._mode = "edit"
        self._robot_id = robot.id
        self._original_robot = robot
        self._title_label.setText("添加/编辑机器人")
        self._load_robot(robot)
        self.advanced_checkbox.setChecked(False)

    def _set_advanced_visible(self, visible: bool) -> None:
        self.advanced_widget.setVisible(visible)
        if not self._layout_ready:
            return
        self.adjustSize()
        window = self.window()
        if window is not self:
            window.adjustSize()

    def _load_robot(self, robot: RobotInfo) -> None:
        self.name_edit.setText(robot.name)
        self.uri_edit.setText(robot.master_uri)
        self.joystick_edit.setText(robot.joystick_topic)
        self.laser_edit.setText(robot.laser_topic)
        self.camera_edit.setText(robot.camera_topic)
        self.navsat_edit.setText(robot.navsat_topic)
        self.odometry_edit.setText(robot.odometry_topic)
        self.pose_edit.setText(robot.pose_topic)
        self.reverse_laser_checkbox.setChecked(robot.reverse_laser_scan)
        self.invert_x_checkbox.setChecked(robot.invert_x)
        self.invert_y_checkbox.setChecked(robot.invert_y)
        self.invert_angular_checkbox.setChecked(robot.invert_angular_velocity)

    def _show_validation_error(self, message: str) -> None:
        QMessageBox.warning(self, "添加/编辑机器人", message)

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        master_uri = self.uri_edit.text().strip()
        joystick_topic = self.joystick_edit.text().strip()
        laser_topic = self.laser_edit.text().strip()
        camera_topic = self.camera_edit.text().strip()
        navsat_topic = self.navsat_edit.text().strip()
        odometry_topic = self.odometry_edit.text().strip()
        pose_topic = self.pose_edit.text().strip()

        if not name:
            self._show_validation_error("机器人名称不能为空。")
            self.name_edit.setFocus()
            return
        if not master_uri:
            self._show_validation_error("Master URI 不能为空。")
            self.uri_edit.setFocus()
            return
        if not master_uri.startswith(("http://", "https://")):
            self._show_validation_error("Master URI 需要以 http:// 或 https:// 开头。")
            self.uri_edit.setFocus()
            return
        if not all(
            [
                joystick_topic,
                laser_topic,
                camera_topic,
                navsat_topic,
                odometry_topic,
                pose_topic,
            ]
        ):
            self._show_validation_error("高级选项里的话题不能为空。")
            self.advanced_checkbox.setChecked(True)
            return

        if self._mode == "edit" and self._robot_id:
            robot_id = self._robot_id
        else:
            robot_id = RobotInfo.new_id()
        original = self._original_robot
        robot = RobotInfo(
            id=robot_id,
            name=name,
            master_uri=master_uri,
            joystick_topic=joystick_topic,
            camera_topic=camera_topic,
            laser_topic=laser_topic,
            navsat_topic=navsat_topic,
            odometry_topic=odometry_topic,
            pose_topic=pose_topic,
            reverse_laser_scan=self.reverse_laser_checkbox.isChecked(),
            invert_x=self.invert_x_checkbox.isChecked(),
            invert_y=self.invert_y_checkbox.isChecked(),
            invert_angular_velocity=self.invert_angular_checkbox.isChecked(),
            backend_type=original.backend_type if original else "mock",
            gateway_uri=original.gateway_uri if original else "",
            camera_mode=original.camera_mode if original else "mjpeg",
            camera_url=original.camera_url if original else "",
            ros_domain_id=original.ros_domain_id if original else 0,
        )
        self.save_requested.emit(robot)
