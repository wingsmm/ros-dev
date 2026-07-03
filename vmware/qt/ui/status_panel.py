from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class StatusPanel(QWidget):
    def __init__(self, parent=None):
        super(StatusPanel, self).__init__(parent)
        self.master_label = QLabel("ROS Master: -")
        self.ros_ip_label = QLabel("ROS IP: -")
        self.master_state = QLabel("Master: 未知")
        self.rviz_state = QLabel("RViz: 未知")
        self.robot_hint = QLabel("真机: 在小车手动 pc_stack camera-start / full-start")

        info = QVBoxLayout()
        info.addWidget(self.master_label)
        info.addWidget(self.ros_ip_label)
        info.addWidget(self.master_state)
        info.addWidget(self.rviz_state)
        info.addWidget(self.robot_hint)

        self.btn_refresh = QPushButton("刷新状态")
        self.btn_check_env = QPushButton("检查环境")

        actions = QHBoxLayout()
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_check_env)

        box = QGroupBox("环境状态 (VM 本地)")
        layout = QVBoxLayout(box)
        layout.addLayout(info)
        layout.addLayout(actions)

        outer = QVBoxLayout(self)
        outer.addWidget(box)

    def set_master_uri(self, uri):
        self.master_label.setText("ROS Master: %s" % uri)

    def set_ros_ip(self, ip):
        self.ros_ip_label.setText("ROS IP (VM): %s" % (ip or "(未检测)"))

    def set_master_ok(self, ok):
        self.master_state.setText("Master: %s" % ("可达" if ok else "不可达"))
        self.master_state.setStyleSheet("color: green;" if ok else "color: #c0392b;")

    def set_rviz_hint(self, running, pid=0):
        if running:
            self.rviz_state.setText("RViz: 运行中 (本客户端 pid=%s)" % pid)
            self.rviz_state.setStyleSheet("color: green;")
        else:
            self.rviz_state.setText("RViz: 未启动")
            self.rviz_state.setStyleSheet("")
