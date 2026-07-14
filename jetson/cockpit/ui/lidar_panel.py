from __future__ import annotations

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


class LidarPanel(QWidget):
    """Main-window radar panel.

    Modes:
      - 原始点云 / 车体对齐: 启动雷达 / 打开雷达视图 / 停止雷达
      - 雷达/里程计: 启动定位 / 打开定位视图 / 停止定位
    """

    MODE_LIO = "lio"
    MODE_RAW = "raw"
    MODE_BASE = "base"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.summary_label = QLabel("状态：点「启动雷达」后显示点云与 TF 概况")
        self.summary_label.setWordWrap(True)

        mode_caption = QLabel("雷达视图：")
        self.mode_group = QButtonGroup(self)
        self.radio_raw = QRadioButton("原始点云")
        self.radio_base = QRadioButton("车体对齐")
        self.radio_lio = QRadioButton("雷达/里程计")
        self.mode_group.addButton(self.radio_lio, 0)
        self.mode_group.addButton(self.radio_base, 1)
        self.mode_group.addButton(self.radio_raw, 2)
        self.radio_base.setChecked(True)

        mode_layout = QVBoxLayout()
        mode_layout.addWidget(mode_caption)
        mode_layout.addWidget(self.radio_raw)
        mode_layout.addWidget(self.radio_base)
        mode_layout.addWidget(self.radio_lio)

        self.btn_start_radar = QPushButton("启动雷达")
        self.btn_start_rviz = QPushButton("打开雷达视图")
        self.btn_stop_radar = QPushButton("停止雷达")
        main_actions = QHBoxLayout()
        main_actions.addWidget(self.btn_start_radar)
        main_actions.addWidget(self.btn_start_rviz)
        main_actions.addWidget(self.btn_stop_radar)

        self.btn_extrinsics = QPushButton("点云对齐…")
        extr_row = QHBoxLayout()
        extr_row.addStretch(1)
        extr_row.addWidget(self.btn_extrinsics)

        box = QGroupBox("雷达观测")
        layout = QVBoxLayout(box)
        layout.addLayout(mode_layout)
        layout.addLayout(main_actions)
        layout.addWidget(self.summary_label)
        layout.addLayout(extr_row)

        outer = QVBoxLayout(self)
        outer.addWidget(box)
        self._sync_action_labels()

    def selected_mode(self) -> str:
        if self.radio_raw.isChecked():
            return self.MODE_RAW
        if self.radio_base.isChecked():
            return self.MODE_BASE
        return self.MODE_LIO

    def _sync_action_labels(self) -> None:
        if self.selected_mode() == self.MODE_LIO:
            self.btn_start_radar.setText("启动定位")
            self.btn_start_rviz.setText("打开定位视图")
            self.btn_stop_radar.setText("停止定位")
        else:
            self.btn_start_radar.setText("启动雷达")
            self.btn_start_rviz.setText("打开雷达视图")
            self.btn_stop_radar.setText("停止雷达")

    def set_stack_busy(self, busy: bool, phase: str = "") -> None:
        """Disable stack + extrinsics buttons while a remote op is in flight."""
        starting = phase == "start"
        stopping = phase == "stop"
        self.btn_start_radar.setEnabled(not busy)
        self.btn_stop_radar.setEnabled(not busy)
        self.btn_extrinsics.setEnabled(not busy)
        # Mode radios also locked during remote ops
        self.radio_raw.setEnabled(not busy)
        self.radio_base.setEnabled(not busy)
        self.radio_lio.setEnabled(not busy)
        if starting:
            self.btn_start_rviz.setEnabled(not busy)
        elif stopping:
            self.btn_start_rviz.setEnabled(False)
        else:
            self.btn_start_rviz.setEnabled(not busy)

    def set_summary(self, text: str, ok: bool = True) -> None:
        self.summary_label.setText("状态：%s" % text)
        self.summary_label.setStyleSheet("color: green;" if ok else "color: #c0392b;")
