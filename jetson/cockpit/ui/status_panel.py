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
        super().__init__(parent)
        self.domain_label = QLabel("ROS_DOMAIN_ID: -")
        self.cmd_vel_label = QLabel("/cmd_vel: -")
        self.action_label = QLabel("/vehicle/control_action: -")
        self.node_label = QLabel("ROS2 图：未知")

        info = QVBoxLayout()
        info.addWidget(self.domain_label)
        info.addWidget(self.cmd_vel_label)
        info.addWidget(self.action_label)
        info.addWidget(self.node_label)

        self.btn_refresh = QPushButton("刷新状态")
        self.btn_check_env = QPushButton("检查环境")

        actions = QHBoxLayout()
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_check_env)

        box = QGroupBox("连接状态 (ROS2 DDS)")
        layout = QVBoxLayout(box)
        layout.addLayout(info)
        layout.addLayout(actions)

        outer = QVBoxLayout(self)
        outer.addWidget(box)

    def set_domain_id(self, value):
        self.domain_label.setText("ROS_DOMAIN_ID: %s" % value)

    def set_cmd_vel_state(self, ok, text):
        self.cmd_vel_label.setText("/cmd_vel: %s" % text)
        self.cmd_vel_label.setStyleSheet("color: green;" if ok else "color: #c0392b;")

    def set_action_state(self, ok, text):
        self.action_label.setText("/vehicle/control_action: %s" % text)
        self.action_label.setStyleSheet("color: green;" if ok else "color: #c0392b;")

    def set_graph_state(self, ok, text):
        self.node_label.setText("ROS2 图：%s" % text)
        self.node_label.setStyleSheet("color: green;" if ok else "color: #c0392b;")
