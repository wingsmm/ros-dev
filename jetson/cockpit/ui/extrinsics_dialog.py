"""Standalone L1 point-cloud alignment editor dialog.

The main cockpit window only exposes the radar day-to-day flow
(start/open/stop). Editing xyz/rpy for the /unilidar/cloud_aligned rotation
is low-frequency and lives in this dialog so the main panel stays
uncluttered. Remote read/apply run in QThread workers and share the parent
window's _remote_busy lock so radar start/stop cannot race with a YAML
write or cloud_align restart.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.cloud_align_control import (
    CloudAlignApplyResult,
    CloudAlignExtrinsics,
    apply_cloud_align,
    read_cloud_align,
    rpy_deg_from_ext,
)
from core.config import CockpitConfig


class _ReadWorker(QThread):
    finished_extrinsics = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, cfg: CockpitConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg

    def run(self):
        try:
            ok, result = read_cloud_align(cfg=self._cfg)
            if ok and isinstance(result, CloudAlignExtrinsics):
                self.finished_extrinsics.emit(result)
            else:
                self.failed.emit(str(result))
        except Exception as exc:
            self.failed.emit(str(exc))


class _ApplyWorker(QThread):
    finished_result = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        cfg: CockpitConfig,
        xyz: tuple,
        trim_rpy_deg: tuple,
        template: CloudAlignExtrinsics,
        parent=None,
    ):
        super().__init__(parent)
        self._cfg = cfg
        self._xyz = xyz
        self._trim_rpy_deg = trim_rpy_deg
        self._template = template

    def run(self):
        try:
            result = apply_cloud_align(
                self._xyz,
                self._trim_rpy_deg,
                template=self._template,
                cfg=self._cfg,
            )
            self.finished_result.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ExtrinsicsDialog(QDialog):
    """Modal editor for /unilidar/cloud_aligned rotation (xyz + rpy)."""

    applied = pyqtSignal(bool, str)

    def __init__(
        self,
        cfg: CockpitConfig,
        is_remote_busy: Callable[[], bool],
        set_remote_busy: Callable[[bool], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._is_remote_busy = is_remote_busy
        self._set_remote_busy = set_remote_busy
        self._template: Optional[CloudAlignExtrinsics] = None
        self._read_worker: Optional[_ReadWorker] = None
        self._apply_worker: Optional[_ApplyWorker] = None
        self._local_busy = False

        self.setWindowTitle("L1 点云对齐")
        self.resize(520, 360)

        self.write_status_label = QLabel("写入：未操作")
        self.node_status_label = QLabel("对齐节点：未检查")
        self.cloud_status_label = QLabel("点云：未检查")
        status_box = QGroupBox("当前状态")
        status_layout = QVBoxLayout(status_box)
        status_layout.addWidget(self.write_status_label)
        status_layout.addWidget(self.node_status_label)
        status_layout.addWidget(self.cloud_status_label)

        self.spin_x = self._xyz_spin()
        self.spin_y = self._xyz_spin()
        self.spin_z = self._xyz_spin()
        xyz_form = QFormLayout()
        xyz_form.addRow("x", self.spin_x)
        xyz_form.addRow("y", self.spin_y)
        xyz_form.addRow("z", self.spin_z)
        xyz_group = QGroupBox("平移 xyz（米）")
        xyz_group.setLayout(xyz_form)

        self.spin_roll = self._angle_spin()
        self.spin_pitch = self._angle_spin()
        self.spin_yaw = self._angle_spin()
        rpy_form = QFormLayout()
        rpy_form.addRow("roll（左右歪，先调这个）", self.spin_roll)
        rpy_form.addRow("pitch（前后翘，再调这个）", self.spin_pitch)
        rpy_form.addRow("yaw（车头方向偏，最后调）", self.spin_yaw)
        rpy_group = QGroupBox("姿态微调（点云整体旋转）")
        rpy_group.setLayout(rpy_form)

        self.btn_read = QPushButton("读取对齐参数")
        self.btn_apply = QPushButton("应用对齐参数")
        self.btn_apply.setEnabled(False)
        self.btn_close = QPushButton("关闭")
        action_row = QHBoxLayout()
        action_row.addWidget(self.btn_read)
        action_row.addWidget(self.btn_apply)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_close)

        hint = QLabel(
            "这里调的是点云整体，不是坐标轴显示。\n"
            "卧放基准由 Jetson YAML 保管，通常不要改。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")

        root = QVBoxLayout(self)
        root.addWidget(status_box)
        root.addWidget(xyz_group)
        root.addWidget(rpy_group)
        root.addLayout(action_row)
        root.addWidget(hint)

        self.btn_read.clicked.connect(self._trigger_read)
        self.btn_apply.clicked.connect(self._trigger_apply)
        self.btn_close.clicked.connect(self.reject)

        self._trigger_read()

    # ---- helpers -----------------------------------------------------

    @staticmethod
    def _xyz_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-5.0, 5.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.01)
        spin.setSuffix(" m")
        return spin

    @staticmethod
    def _angle_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-180.0, 180.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" deg")
        return spin

    def _style_status(self, label: QLabel, ok):
        if ok is True:
            label.setStyleSheet("color: green;")
        elif ok is False:
            label.setStyleSheet("color: #c0392b;")
        else:
            label.setStyleSheet("color: #666;")

    def _set_write_status(self, text: str, ok=None) -> None:
        self.write_status_label.setText("写入：%s" % text)
        self._style_status(self.write_status_label, ok)

    def _set_node_status(self, text: str, ok=None) -> None:
        self.node_status_label.setText("对齐节点：%s" % text)
        self._style_status(self.node_status_label, ok)

    def _set_cloud_status(self, text: str, ok=None) -> None:
        self.cloud_status_label.setText("点云：%s" % text)
        self._style_status(self.cloud_status_label, ok)

    def _set_local_busy(self, busy: bool) -> None:
        self._local_busy = busy
        for spin in (
            self.spin_x, self.spin_y, self.spin_z,
            self.spin_roll, self.spin_pitch, self.spin_yaw,
        ):
            spin.setEnabled(not busy)
        self.btn_read.setEnabled(not busy)
        # Apply requires a successful read (template known) + not busy.
        self.btn_apply.setEnabled(
            (not busy) and self._template is not None
        )
        self.btn_close.setEnabled(not busy)

    def _acquire_remote(self) -> bool:
        if self._is_remote_busy():
            QMessageBox.information(
                self,
                "远程操作繁忙",
                "有远程操作仍在进行，请稍后再试。",
            )
            return False
        self._set_remote_busy(True)
        self._set_local_busy(True)
        return True

    def _release_remote(self) -> None:
        self._set_remote_busy(False)
        self._set_local_busy(False)

    # ---- read --------------------------------------------------------

    def _trigger_read(self) -> None:
        if self._read_worker is not None and self._read_worker.isRunning():
            return
        if self._apply_worker is not None and self._apply_worker.isRunning():
            return
        if not self._acquire_remote():
            return
        self._set_write_status("读取中…", None)
        self._read_worker = _ReadWorker(self._cfg, self)
        self._read_worker.finished_extrinsics.connect(self._on_read_done)
        self._read_worker.failed.connect(self._on_read_failed)
        self._read_worker.start()

    def _on_read_done(self, ext: CloudAlignExtrinsics) -> None:
        self._template = ext
        self.spin_x.setValue(ext.xyz[0])
        self.spin_y.setValue(ext.xyz[1])
        self.spin_z.setValue(ext.xyz[2])
        rpy_deg = rpy_deg_from_ext(ext)
        self.spin_roll.setValue(rpy_deg[0])
        self.spin_pitch.setValue(rpy_deg[1])
        self.spin_yaw.setValue(rpy_deg[2])
        self._set_write_status("已从 Jetson 读取", True)
        self._release_remote()

    def _on_read_failed(self, text: str) -> None:
        self._template = None
        self._set_write_status("读取失败", False)
        self._release_remote()
        QMessageBox.warning(
            self,
            "读取对齐参数失败",
            "无法读取 Jetson 上的 l1_cloud_align.yaml。\n\n%s" % text,
        )

    # ---- apply -------------------------------------------------------

    def _trigger_apply(self) -> None:
        if self._apply_worker is not None and self._apply_worker.isRunning():
            return
        if self._template is None:
            QMessageBox.warning(
                self,
                "请先读取对齐参数",
                "应用对齐参数前请先点「读取对齐参数」，以保留 Jetson 上的 topic/frame 配置。",
            )
            return
        if not self._acquire_remote():
            return
        xyz = (
            self.spin_x.value(),
            self.spin_y.value(),
            self.spin_z.value(),
        )
        trim_rpy_deg = (
            self.spin_roll.value(),
            self.spin_pitch.value(),
            self.spin_yaw.value(),
        )
        self._set_write_status("写入中…", None)
        self._set_node_status("重启中…", None)
        self._apply_worker = _ApplyWorker(
            self._cfg,
            xyz,
            trim_rpy_deg,
            self._template,
            self,
        )
        self._apply_worker.finished_result.connect(self._on_apply_done)
        self._apply_worker.failed.connect(self._on_apply_failed)
        self._apply_worker.start()

    def _on_apply_done(self, result: CloudAlignApplyResult) -> None:
        if result.write_ok:
            self._set_write_status("成功", True)
        else:
            self._set_write_status("失败", False)
        if result.restart_ok:
            self._set_node_status("正常", True)
        else:
            self._set_node_status("重启失败", False)
        self._release_remote()
        message = "write=%s restart=%s" % (result.write_detail, result.restart_detail)
        self.applied.emit(result.ok, message)

    def _on_apply_failed(self, text: str) -> None:
        self._set_write_status("失败", False)
        self._set_node_status("重启失败", False)
        self._release_remote()
        self.applied.emit(False, text)
        QMessageBox.warning(
            self,
            "应用对齐参数失败",
            "写入 YAML 或重启 l1_cloud_align 失败。\n\n%s" % text,
        )

    # ---- lifecycle ---------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._local_busy:
            event.ignore()
            QMessageBox.information(
                self,
                "远程操作繁忙",
                "有远程操作仍在进行，请稍后再关闭。",
            )
            return
        super().closeEvent(event)

    def reject(self) -> None:  # noqa: D401 - Qt API override
        if self._local_busy:
            QMessageBox.information(
                self,
                "远程操作繁忙",
                "有远程操作仍在进行，请稍后再关闭。",
            )
            return
        super().reject()
