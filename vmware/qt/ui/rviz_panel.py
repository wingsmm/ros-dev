from PyQt5.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class RvizPanel(QWidget):
    def __init__(self, config_labels, parent=None):
        super(RvizPanel, self).__init__(parent)
        self.config_path_label = QLabel("当前配置: -")
        self.config_path_label.setWordWrap(True)

        self.group = QButtonGroup(self)
        self.radios = {}
        layout_choices = QVBoxLayout()
        for idx, label in enumerate(config_labels):
            radio = QRadioButton(label)
            self.group.addButton(radio, idx)
            self.radios[label] = radio
            layout_choices.addWidget(radio)
            if idx == 1:
                radio.setChecked(True)

        self.btn_start = QPushButton("启动 RViz (本机 VM)")
        self.btn_stop = QPushButton("停止 RViz")

        actions = QHBoxLayout()
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_stop)

        note = QLabel(
            "RViz 在本 VM 运行，连真机 master。\n"
            "雷达/里程计：Fixed Frame=odom，看 /scan；真机 radar2d-start 或 full-start。\n"
            "深度轻量：深度卡顿验收；RViz 小预览 + RGB/深度 image_view 大图。\n"
            "RGB+Depth 诊断：RGB+深度+TF 同屏排错；同样自动开 image_view 大图。\n"
            "深度增强：需真机 camera-deep-start；RGB/Depth/Preview image_view + "
            "VM 本地点云 + 相机 static TF。RViz Fixed Frame=base_link。"
        )
        note.setWordWrap(True)

        box = QGroupBox("RViz (VM 本地)")
        layout = QVBoxLayout(box)
        layout.addLayout(layout_choices)
        layout.addWidget(self.config_path_label)
        layout.addLayout(actions)
        layout.addWidget(note)

        outer = QVBoxLayout(self)
        outer.addWidget(box)

    def selected_label(self):
        btn = self.group.checkedButton()
        return btn.text() if btn else ""

    def set_config_path(self, path):
        self.config_path_label.setText("当前配置: %s" % path)
