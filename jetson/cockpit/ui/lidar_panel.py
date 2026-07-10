from PyQt5.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LidarPanel(QWidget):
    MODE_LIO = "lio"
    MODE_RAW = "raw"
    MODE_BASE = "base"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.summary_label = QLabel("状态：未检查（点「高级诊断」或打开 RViz 后再看）")
        self.summary_label.setWordWrap(True)

        self.mode_group = QButtonGroup(self)
        self.radio_lio = QRadioButton("雷达/里程计")
        self.radio_base = QRadioButton("车体对齐")
        self.radio_raw = QRadioButton("原始点云")
        self.mode_group.addButton(self.radio_lio, 0)
        self.mode_group.addButton(self.radio_base, 1)
        self.mode_group.addButton(self.radio_raw, 2)
        self.radio_raw.setChecked(True)

        mode_layout = QVBoxLayout()
        mode_layout.addWidget(self.radio_raw)
        mode_layout.addWidget(self.radio_base)
        mode_layout.addWidget(self.radio_lio)

        self.config_path_label = QLabel("当前配置：-")

        self.btn_start_rviz = QPushButton("启动 RViz (本地)")
        self.btn_stop_rviz = QPushButton("停止 RViz")

        actions = QHBoxLayout()
        actions.addWidget(self.btn_start_rviz)
        actions.addWidget(self.btn_stop_rviz)

        self.btn_toggle_diag = QPushButton("高级诊断 ▼")
        self.btn_toggle_diag.setCheckable(True)

        self._diag_box = QWidget()
        self._diag_box.setVisible(False)
        diag_layout = QVBoxLayout(self._diag_box)
        diag_layout.setContentsMargins(0, 0, 0, 0)
        self.diag_detail = QTextEdit()
        self.diag_detail.setReadOnly(True)
        self.diag_detail.setMaximumHeight(140)
        self.diag_detail.setPlaceholderText("Topic / Hz / Jetson port / LIO 详情")
        self.btn_diag_refresh = QPushButton("刷新诊断")
        diag_layout.addWidget(self.diag_detail)
        diag_layout.addWidget(self.btn_diag_refresh)

        note = QLabel(
            "原始点云：unilidar.rviz；车体对齐：unilidar_base.rviz；"
            "雷达/里程计：unilidar_mapping.rviz（阶段 4）。"
        )
        note.setWordWrap(True)

        box = QGroupBox("雷达观测")
        layout = QVBoxLayout(box)
        layout.addLayout(mode_layout)
        layout.addWidget(self.config_path_label)
        layout.addLayout(actions)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.btn_toggle_diag)
        layout.addWidget(self._diag_box)
        layout.addWidget(note)

        outer = QVBoxLayout(self)
        outer.addWidget(box)

        self.btn_toggle_diag.toggled.connect(self._on_toggle_diag)

    def _on_toggle_diag(self, checked: bool) -> None:
        self._diag_box.setVisible(checked)
        self.btn_toggle_diag.setText("高级诊断 ▲" if checked else "高级诊断 ▼")

    def selected_mode(self) -> str:
        if self.radio_raw.isChecked():
            return self.MODE_RAW
        if self.radio_base.isChecked():
            return self.MODE_BASE
        return self.MODE_LIO

    def set_config_path(self, path: str) -> None:
        self.config_path_label.setText("当前配置：%s" % path)

    def set_summary(self, text: str, ok: bool = True) -> None:
        self.summary_label.setText("状态：%s" % text)
        self.summary_label.setStyleSheet("color: green;" if ok else "color: #c0392b;")

    def set_diag_detail(self, text: str) -> None:
        self.diag_detail.setPlainText(text)
