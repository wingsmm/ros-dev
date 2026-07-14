"""Jetson Qt cockpit for the dry-run /cmd_vel bridge."""

from __future__ import annotations

import logging
import os
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import CockpitConfig, app_root
from core.l1_lio_control import run_l1_lio
from core.l1_stack_control import run_l1_stack
from core.ros2_lidar_probe import probe_lidar_status, probe_lio_status, probe_static_tf
from core.ros2_probe import (
    env_check_report,
    format_topic_report,
    format_topic_summary,
    probe_key_topics,
    ros2_node_list,
    topic_status,
)
from core.ros2_control import Ros2ControlWorker
from core.rviz_process import RvizProcessManager, rviz2_start_command
from ui.extrinsics_dialog import ExtrinsicsDialog
from ui.lidar_panel import LidarPanel
from ui.status_panel import StatusPanel
from ui.teleop_panel import TeleopPanel
from ui.topic_panel import TopicPanel


class TextWorker(QThread):
    finished_text = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.finished_text.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class TopicWorker(QThread):
    finished_topics = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, topics, parent=None):
        super().__init__(parent)
        self._topics = topics

    def run(self):
        try:
            self.finished_topics.emit(probe_key_topics(self._topics))
        except Exception as exc:
            self.failed.emit(str(exc))


class LidarWorker(QThread):
    finished_status = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, cfg: CockpitConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg

    def run(self):
        try:
            root = app_root()
            raw = probe_lidar_status(
                self._cfg.lidar_cloud_topic,
                self._cfg.lidar_imu_topic,
                root,
                cloud_aligned_topic=self._cfg.lidar_cloud_aligned_topic,
            )
            lio = probe_lio_status(
                self._cfg.lio_odom_topic,
                self._cfg.lio_path_topic,
                self._cfg.lio_cloud_registered_topic,
                root,
                cfg=self._cfg,
            )
            self.finished_status.emit(raw, lio)
        except Exception as exc:
            self.failed.emit(str(exc))


class RvizPrecheckWorker(QThread):
    """Lightweight cloud publisher (+ TF) check before opening RViz."""

    finished_check = pyqtSignal(bool, bool, bool)  # cloud_ok, tf_ok, aligned_ok
    failed = pyqtSignal(str)

    def __init__(self, cloud_topic: str, aligned_topic: str, parent=None):
        super().__init__(parent)
        self._cloud_topic = cloud_topic
        self._aligned_topic = aligned_topic

    def run(self):
        try:
            row_cloud = topic_status(self._cloud_topic)
            row_aligned = topic_status(self._aligned_topic)
            tf_ok, _detail = probe_static_tf("base_link", "unilidar_lidar")
            self.finished_check.emit(
                row_cloud.has_publisher, tf_ok, row_aligned.has_publisher
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class LioRvizPrecheckWorker(QThread):
    """Localization view requires registered cloud, odom, path, and odom->base_link."""

    finished_check = pyqtSignal(bool, object)  # ok, missing list
    failed = pyqtSignal(str)

    def __init__(
        self,
        cloud_registered: str,
        odom_topic: str,
        path_topic: str,
        odom_frame: str,
        base_frame: str = "base_link",
        parent=None,
    ):
        super().__init__(parent)
        self._cloud_registered = cloud_registered
        self._odom_topic = odom_topic
        self._path_topic = path_topic
        self._odom_frame = odom_frame
        self._base_frame = base_frame

    def run(self):
        try:
            from core.ros2_lidar_probe import probe_lio_mapping_ready

            ok, missing = probe_lio_mapping_ready(
                self._cloud_registered,
                self._odom_topic,
                self._path_topic,
                self._odom_frame,
                self._base_frame,
            )
            self.finished_check.emit(ok, missing)
        except Exception as exc:
            self.failed.emit(str(exc))


class L1StackWorker(QThread):
    finished_result = pyqtSignal(str, bool, str)
    failed = pyqtSignal(str)

    def __init__(self, cfg: CockpitConfig, action: str, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._action = action

    def run(self):
        try:
            ok, text = run_l1_stack(self._action, cfg=self._cfg)
            self.finished_result.emit(self._action, ok, text)
        except Exception as exc:
            self.failed.emit(str(exc))


class L1LioWorker(QThread):
    finished_result = pyqtSignal(str, bool, str)
    failed = pyqtSignal(str)

    def __init__(self, cfg: CockpitConfig, action: str, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._action = action

    def run(self):
        try:
            ok, text = run_l1_lio(self._action, cfg=self._cfg)
            self.finished_result.emit(self._action, ok, text)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, cfg: CockpitConfig, log_path) -> None:
        super().__init__()
        self.setWindowTitle("Jetson Qt 控制台")
        self.resize(720, 560)
        self._cfg = cfg

        self._worker = Ros2ControlWorker(
            cmd_vel_topic=cfg.cmd_vel_topic,
            control_action_topic=cfg.control_action_topic,
            parent=self,
        )
        self._worker.status_changed.connect(self._set_status)
        self._worker.line.connect(self._append_log)
        self._worker.action_received.connect(self._on_action_received)

        self._status = QLabel("ROS2：启动中")
        self._last_action = QLabel("动作回显：-")
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._status_panel = StatusPanel()
        self._topic_panel = TopicPanel()
        self._lidar_panel = LidarPanel()
        self._rviz_mgr = RvizProcessManager(self)
        self._rviz_mgr.output.connect(self._append_log)
        self._rviz_mgr.running_changed.connect(self._on_rviz_running_changed)
        self._teleop_panel = TeleopPanel(
            linear_speed=cfg.teleop_linear_speed,
            angular_speed=cfg.teleop_angular_speed,
            repeat_hz=cfg.teleop_repeat_hz,
        )
        self._teleop_panel.velocity_requested.connect(self._on_teleop_velocity)
        self._teleop_panel.stop_requested.connect(self._on_teleop_stop)
        self._teleop_panel.set_keyboard_enabled(cfg.teleop_enable_keyboard)
        self._log_path = log_path
        self._env_worker = None
        self._topic_worker = None
        self._lidar_worker = None
        self._rviz_precheck_worker = None
        self._l1_stack_worker = None
        self._l1_lio_worker = None
        self._lio_rviz_precheck_worker = None
        self._lidar_summary_line = ""
        self._lidar_summary_ok = True
        self._last_lidar_status = None
        self._last_lio_status = None
        self._radar_running: bool | None = None
        self._loc_running: bool | None = None
        self._remote_busy = False
        self._extrinsics_dialog: ExtrinsicsDialog | None = None
        self._rviz_label = ""
        self._closing = False

        self._build_ui()
        self._wire()
        self._teleop_panel.set_controls_enabled(False, "ROS2 启动中，遥控暂不可用。")
        self._worker.start()
        self._refresh_status()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        header = QGroupBox("Jetson ROS2 干跑控制链路")
        header_layout = QVBoxLayout(header)
        hint = QLabel(
            "PC/WSL 侧 Qt 控制台发布 /cmd_vel；Jetson ros2_ws 转译为 "
            "FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP，并通过 "
            "/vehicle/control_action 回显。本阶段不调用 car_web，不驱动真实硬件。"
        )
        hint.setWordWrap(True)
        header_layout.addWidget(hint)
        header_layout.addWidget(self._status)
        header_layout.addWidget(self._last_action)
        header_layout.addWidget(QLabel("日志文件：%s" % self._log_path))
        root.addWidget(header)

        root.addWidget(self._status_panel)
        root.addWidget(self._lidar_panel)
        root.addWidget(self._teleop_panel)
        root.addWidget(self._topic_panel)

        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(self._log)
        root.addWidget(log_group, 1)

        self.setCentralWidget(central)

    def _wire(self) -> None:
        self._status_panel.btn_refresh.clicked.connect(self._refresh_status)
        self._status_panel.btn_check_env.clicked.connect(self._run_env_check)
        self._topic_panel.btn_probe.clicked.connect(self._probe_topics)
        self._lidar_panel.mode_group.buttonClicked.connect(self._on_lidar_mode_changed)
        self._lidar_panel.btn_start_radar.clicked.connect(self._start_radar)
        self._lidar_panel.btn_stop_radar.clicked.connect(self._stop_radar)
        self._lidar_panel.btn_start_rviz.clicked.connect(self._start_lidar_rviz)
        self._lidar_panel.btn_extrinsics.clicked.connect(self._open_extrinsics_dialog)

    def _on_lidar_mode_changed(self, _button) -> None:
        self._lidar_panel._sync_action_labels()
        if self._lidar_summary_line:
            self._update_lidar_summary_display()

    def _open_extrinsics_dialog(self) -> None:
        if self._extrinsics_dialog is not None and self._extrinsics_dialog.isVisible():
            self._extrinsics_dialog.raise_()
            self._extrinsics_dialog.activateWindow()
            return
        dialog = ExtrinsicsDialog(
            cfg=self._cfg,
            is_remote_busy=lambda: self._remote_busy,
            set_remote_busy=self._set_remote_busy,
            parent=self,
        )
        dialog.applied.connect(self._on_extrinsics_applied)
        self._extrinsics_dialog = dialog
        try:
            dialog.exec_()
        finally:
            self._extrinsics_dialog = None

    def _on_extrinsics_applied(self, ok: bool, detail: str) -> None:
        if self._closing:
            return
        if ok:
            self._append_log("应用外参成功：%s" % detail)
        else:
            self._append_log("[ERR] 应用外参：%s" % detail)
        self._refresh_lidar_status()

    def _start_radar(self) -> None:
        if self._lidar_panel.selected_mode() == LidarPanel.MODE_LIO:
            self._run_l1_lio("start", busy_label="定位启动中…")
        else:
            self._run_l1_stack("start", busy_label="雷达启动中…")

    def _stop_radar(self) -> None:
        if self._lidar_panel.selected_mode() == LidarPanel.MODE_LIO:
            self._run_l1_lio("stop", busy_label="定位停止中…")
        else:
            self._run_l1_stack("stop", busy_label="雷达停止中…")

    def _run_l1_stack(self, action: str, busy_label: str) -> None:
        if self._remote_busy:
            self._append_log("远程操作仍在进行")
            return
        self._set_remote_busy(True, phase=action)
        self._lidar_panel.set_summary(busy_label, False)
        self._append_log("Jetson L1：%s" % action)
        self._l1_stack_worker = L1StackWorker(self._cfg, action, self)
        self._l1_stack_worker.finished_result.connect(self._on_l1_stack_done)
        self._l1_stack_worker.failed.connect(self._on_l1_stack_failed)
        self._l1_stack_worker.start()

    def _run_l1_lio(self, action: str, busy_label: str) -> None:
        if self._remote_busy:
            self._append_log("远程操作仍在进行")
            return
        self._set_remote_busy(True, phase=action)
        self._lidar_panel.set_summary(busy_label, False)
        self._append_log("Jetson 定位：%s" % action)
        self._l1_lio_worker = L1LioWorker(self._cfg, action, self)
        self._l1_lio_worker.finished_result.connect(self._on_l1_lio_done)
        self._l1_lio_worker.failed.connect(self._on_l1_lio_failed)
        self._l1_lio_worker.start()

    def _on_l1_stack_done(self, action: str, ok: bool, text: str) -> None:
        if self._closing:
            return
        self._set_remote_busy(False)
        if action == "start":
            self._radar_running = ok or ("L1=running" in text)
        elif action == "stop":
            self._radar_running = False
            if self._rviz_mgr.running:
                self._close_local_rviz()
        if ok:
            self._append_log("Jetson L1 %s: %s" % (action, text))
        else:
            self._append_log("[ERR] Jetson L1 %s: %s" % (action, text))
            self._lidar_panel.set_summary("雷达%s失败" % action, False)
        self._refresh_lidar_status()

    def _on_l1_stack_failed(self, text: str) -> None:
        if self._closing:
            return
        self._set_remote_busy(False)
        self._lidar_panel.set_summary("雷达操作失败", False)
        self._append_log("[ERR] Jetson L1 操作失败：%s" % text)

    def _on_l1_lio_done(self, action: str, ok: bool, text: str) -> None:
        if self._closing:
            return
        self._set_remote_busy(False)
        if action == "start":
            self._loc_running = ok or ("LIO=running" in text and "adapter=running" in text)
            self._radar_running = self._loc_running or ("L1=running" in text)
        elif action == "stop":
            self._loc_running = False
            self._radar_running = False
            if self._rviz_mgr.running:
                self._close_local_rviz()
        if ok:
            self._append_log("Jetson 定位 %s:\n%s" % (action, text))
        else:
            self._append_log("[ERR] Jetson 定位 %s:\n%s" % (action, text))
            self._lidar_panel.set_summary("定位%s失败" % action, False)
        self._refresh_lidar_status()

    def _on_l1_lio_failed(self, text: str) -> None:
        if self._closing:
            return
        self._set_remote_busy(False)
        self._lidar_panel.set_summary("定位操作失败", False)
        self._append_log("[ERR] Jetson 定位操作失败：%s" % text)

    def _set_remote_busy(self, busy: bool, phase: str = "") -> None:
        """Serialize Jetson SSH/YAML operations so TF/L1 state cannot race."""
        self._remote_busy = busy
        self._lidar_panel.set_stack_busy(busy, phase=phase)
    def _refresh_status(self) -> None:
        self._status_panel.set_domain_id(
            os.environ.get("ROS_DOMAIN_ID", "(未设置)")
        )
        ok, nodes = ros2_node_list(timeout=4)
        if ok:
            self._status_panel.set_graph_state(True, "可查询 (%s)" % nodes.splitlines()[0])
        else:
            self._status_panel.set_graph_state(False, nodes)
        rows = probe_key_topics(self._key_topics())
        for row in rows:
            if row.topic == self._cfg.cmd_vel_topic:
                self._status_panel.set_cmd_vel_state(
                    row.has_subscriber,
                    "subscriber OK" if row.has_subscriber else "无 subscriber",
                )
            elif row.topic == self._cfg.control_action_topic:
                self._status_panel.set_action_state(
                    row.has_publisher,
                    "publisher OK" if row.has_publisher else "无 publisher",
                )
        self._topic_panel.set_summary(
            format_topic_summary(
                rows,
                self._cfg.cmd_vel_topic,
                self._cfg.control_action_topic,
            )
        )

    def _key_topics(self) -> list[str]:
        return [self._cfg.cmd_vel_topic, self._cfg.control_action_topic]

    def _run_env_check(self) -> None:
        if self._env_worker is not None and self._env_worker.isRunning():
            self._append_log("环境检查仍在进行")
            return
        self._append_log("开始检查 ROS2 环境")
        self._env_worker = TextWorker(env_check_report, self)
        self._env_worker.finished_text.connect(self._on_env_check_done)
        self._env_worker.failed.connect(self._on_env_check_failed)
        self._env_worker.start()

    def _on_env_check_done(self, text: str) -> None:
        self._topic_panel.set_detail(text)
        self._append_log("环境检查完成")
        self._refresh_status()

    def _on_env_check_failed(self, text: str) -> None:
        self._topic_panel.set_detail("[ERR] %s" % text)
        self._append_log("环境检查失败：%s" % text)

    def _probe_topics(self) -> None:
        if self._topic_worker is not None and self._topic_worker.isRunning():
            self._append_log("Topic 检查仍在进行")
            return
        self._topic_panel.set_detail("检查中...")
        self._topic_worker = TopicWorker(self._key_topics(), self)
        self._topic_worker.finished_topics.connect(self._on_topics_done)
        self._topic_worker.failed.connect(self._on_topics_failed)
        self._topic_worker.start()

    def _on_topics_done(self, rows) -> None:
        self._topic_panel.set_summary(
            format_topic_summary(
                rows,
                self._cfg.cmd_vel_topic,
                self._cfg.control_action_topic,
            )
        )
        self._topic_panel.set_detail(format_topic_report(rows))
        self._append_log("Topic 检查完成")
        self._refresh_status()

    def _on_topics_failed(self, text: str) -> None:
        self._topic_panel.set_detail("[ERR] %s" % text)
        self._append_log("Topic 检查失败：%s" % text)

    def _refresh_lidar_status(self) -> None:
        if self._lidar_worker is not None and self._lidar_worker.isRunning():
            return
        self._lidar_panel.set_summary("检查中...", False)
        self._lidar_worker = LidarWorker(self._cfg, self)
        self._lidar_worker.finished_status.connect(self._on_lidar_status_done)
        self._lidar_worker.failed.connect(self._on_lidar_status_failed)
        self._lidar_worker.start()

    @staticmethod
    def _one_line_lidar_summary(
        status,
        lio_status,
        mode: str,
        rviz_open: bool = False,
        radar_running: bool | None = None,
        loc_running: bool | None = None,
    ) -> tuple[str, bool]:
        if mode == LidarPanel.MODE_LIO:
            parts = []
            if loc_running is True or (
                lio_status.odom_ok and lio_status.cloud_reg_ok
            ):
                parts.append("定位运行中")
            elif loc_running is False:
                parts.append("定位已停止")
            else:
                parts.append("定位未启动")
            if lio_status.odom_ok:
                if lio_status.odom_hz:
                    parts.append("odom %.1fHz" % lio_status.odom_hz)
                else:
                    parts.append("odom 在线")
            else:
                parts.append("odom 无")
            if lio_status.cloud_reg_ok:
                if lio_status.cloud_reg_hz:
                    parts.append("配准 %.1fHz" % lio_status.cloud_reg_hz)
                else:
                    parts.append("配准在线")
            else:
                parts.append("配准无")
            if "adapter=running" in lio_status.jetson_lio:
                parts.append("adapter 运行中")
            if rviz_open:
                parts.append("视图已打开")
            ok = bool(lio_status.odom_ok and lio_status.cloud_reg_ok and lio_status.path_has_pub)
            return " · ".join(parts), ok

        if mode == LidarPanel.MODE_BASE:
            if status.aligned_ok:
                cloud = "对齐点云在线"
            elif status.cloud_ok:
                cloud = "原始点云在线，对齐未就绪"
            else:
                cloud = "点云无"
        elif status.cloud_hz:
            cloud = "点云 %.1fHz" % status.cloud_hz
        elif status.cloud_ok:
            cloud = "点云在线"
        else:
            cloud = "点云无"
        tf = "TF 正常" if status.tf_ok else "TF 缺失(仅坐标轴)"
        if radar_running is True:
            radar = "雷达运行中"
        elif radar_running is False:
            radar = "雷达已停止"
        elif status.cloud_publisher not in ("", "-"):
            radar = "雷达运行中"
        else:
            radar = "雷达未启动"
        parts = [cloud, tf, radar]
        if rviz_open:
            parts.append("视图已打开")

        if mode == LidarPanel.MODE_BASE:
            ok = status.aligned_ok
        else:
            ok = status.cloud_ok
        return " · ".join(parts), ok

    def _update_lidar_summary_display(self, rviz_extra: str = "") -> None:
        text = self._lidar_summary_line + rviz_extra
        self._lidar_panel.set_summary(text, self._lidar_summary_ok)

    def _on_lidar_status_done(self, status, lio_status) -> None:
        if self._closing:
            return
        self._last_lidar_status = status
        self._last_lio_status = lio_status
        if status.cloud_publisher not in ("", "-"):
            self._radar_running = True
        elif self._radar_running is None:
            self._radar_running = False
        if lio_status.odom_ok and lio_status.cloud_reg_ok:
            self._loc_running = True

        rviz_open = self._rviz_mgr.running
        self._lidar_summary_line, self._lidar_summary_ok = (
            self._one_line_lidar_summary(
                status,
                lio_status,
                self._lidar_panel.selected_mode(),
                rviz_open,
                self._radar_running,
                self._loc_running,
            )
        )
        self._update_lidar_summary_display()

        if not self._lidar_summary_ok:
            detail = status.detail if self._lidar_panel.selected_mode() != LidarPanel.MODE_LIO else lio_status.detail
            self._append_log("雷达诊断：%s" % detail)

    def _on_lidar_status_failed(self, text: str) -> None:
        if self._closing:
            return
        self._lidar_panel.set_summary("诊断失败: %s" % text, False)
        self._append_log("雷达诊断失败：%s" % text)
    def _open_rviz(self, cfg_path, label: str) -> None:
        if not cfg_path.is_file():
            self._append_log("RViz 配置不存在：%s" % cfg_path)
            return
        self._rviz_label = label
        cmd = rviz2_start_command(cfg_path)
        if self._rviz_mgr.start(cmd, str(cfg_path), process_label=label):
            self._refresh_lidar_status()
            self._append_log("已打开雷达视图（%s）" % label)

    def _selected_lidar_rviz(self):
        mode = self._lidar_panel.selected_mode()
        if mode == LidarPanel.MODE_RAW:
            return self._cfg.rviz_config, "原始点云"
        if mode == LidarPanel.MODE_BASE:
            return self._cfg.lidar_base_rviz, "车体对齐"
        return self._cfg.lidar_mapping_rviz, "雷达/里程计"

    def _start_lidar_rviz(self) -> None:
        if self._remote_busy:
            self._append_log("远程操作仍在进行，稍后再打开视图")
            return
        mode = self._lidar_panel.selected_mode()
        if mode == LidarPanel.MODE_LIO:
            if (
                self._lio_rviz_precheck_worker is not None
                and self._lio_rviz_precheck_worker.isRunning()
            ):
                return
            self._lidar_panel.btn_start_rviz.setEnabled(False)
            self._lio_rviz_precheck_worker = LioRvizPrecheckWorker(
                self._cfg.lio_cloud_registered_topic,
                self._cfg.lio_odom_topic,
                self._cfg.lio_path_topic,
                self._cfg.lio_fixed_frame,
                "base_link",
                self,
            )
            self._lio_rviz_precheck_worker.finished_check.connect(
                self._on_lio_rviz_precheck_done
            )
            self._lio_rviz_precheck_worker.failed.connect(self._on_lio_rviz_precheck_failed)
            self._lio_rviz_precheck_worker.start()
            return

        if (
            self._rviz_precheck_worker is not None
            and self._rviz_precheck_worker.isRunning()
        ):
            return
        self._lidar_panel.btn_start_rviz.setEnabled(False)
        self._rviz_precheck_worker = RvizPrecheckWorker(
            self._cfg.lidar_cloud_topic,
            self._cfg.lidar_cloud_aligned_topic,
            self,
        )
        self._rviz_precheck_worker.finished_check.connect(self._on_rviz_precheck_done)
        self._rviz_precheck_worker.failed.connect(self._on_rviz_precheck_failed)
        self._rviz_precheck_worker.start()

    def _on_lio_rviz_precheck_done(self, ok: bool, missing) -> None:
        if self._closing:
            return
        self._lidar_panel.btn_start_rviz.setEnabled(not self._remote_busy)
        if not ok:
            items = "\n".join("- %s" % m for m in (missing or []))
            QMessageBox.warning(
                self,
                "定位视图未就绪",
                "以下条件未满足，已拒绝打开 RViz：\n%s\n\n请先点「启动定位」。"
                % items,
            )
            self._append_log("打开定位视图被拒绝：%s" % "；".join(missing or []))
            return
        cfg_path, label = self._selected_lidar_rviz()
        self._open_rviz(cfg_path, label)

    def _on_lio_rviz_precheck_failed(self, text: str) -> None:
        if self._closing:
            return
        self._lidar_panel.btn_start_rviz.setEnabled(not self._remote_busy)
        QMessageBox.warning(
            self,
            "定位探测失败",
            "无法确认定位 topic/TF 状态，未打开视图。\n\n%s" % text,
        )
        self._append_log("定位探测失败，未打开视图：%s" % text)

    def _on_rviz_precheck_done(self, has_publisher: bool, tf_ok: bool, aligned_ok: bool) -> None:
        if self._closing:
            return
        self._lidar_panel.btn_start_rviz.setEnabled(not self._remote_busy)
        if not has_publisher:
            QMessageBox.warning(
                self,
                "请先启动雷达",
                "未检测到 /unilidar/cloud publisher。\n请先点「启动雷达」。",
            )
            self._append_log("打开雷达视图被拒绝：无点云 publisher")
            return

        mode = self._lidar_panel.selected_mode()
        if mode == LidarPanel.MODE_BASE:
            if not aligned_ok:
                QMessageBox.information(
                    self,
                    "对齐点云未就绪",
                    "未检测到 /unilidar/cloud_aligned publisher。\n"
                    "l1_cloud_align 可能没跑。可先打开视图，再点「启动雷达」或「点云对齐…」。",
                )
                self._append_log("提示：车体对齐模式下缺 /unilidar/cloud_aligned")
            elif not tf_ok:
                QMessageBox.information(
                    self,
                    "TF 缺失",
                    "已有对齐点云，但 base_link → unilidar_lidar 缺失。\n"
                    "可先打开视图；若不影响画面可忽略。",
                )
                self._append_log("提示：车体对齐模式下 TF 缺失，仍打开视图")

        cfg_path, label = self._selected_lidar_rviz()
        self._open_rviz(cfg_path, label)

    def _on_rviz_precheck_failed(self, text: str) -> None:
        if self._closing:
            return
        self._lidar_panel.btn_start_rviz.setEnabled(not self._remote_busy)
        QMessageBox.warning(
            self,
            "点云探测失败",
            "无法确认 /unilidar/cloud 状态，未打开雷达视图。\n"
            "请检查 ROS_DOMAIN_ID / DDS。\n\n%s" % text,
        )
        self._append_log("点云探测失败，未打开视图：%s" % text)
    def _close_local_rviz(self) -> None:
        self._rviz_mgr.stop()
        stop_script = app_root() / "scripts" / "stop_unilidar_rviz.sh"
        if stop_script.is_file():
            subprocess.run(["bash", str(stop_script)], check=False)
        self._rviz_label = ""

    def _on_rviz_running_changed(self, running: bool) -> None:
        if self._lidar_summary_line:
            self._refresh_lidar_status()
        elif running:
            self._lidar_panel.set_summary("雷达视图已打开", True)
        else:
            self._lidar_panel.set_summary("雷达视图未启动", True)

    def _set_status(self, text: str, ready: bool) -> None:
        self._status.setText(f"ROS2：{text}")
        if ready:
            self._teleop_panel.set_controls_enabled(True)
            self._teleop_panel.set_keyboard_enabled(self._cfg.teleop_enable_keyboard)
        else:
            self._teleop_panel.set_controls_enabled(False, f"ROS2：{text}")

    def _append_log(self, text: str) -> None:
        self._log.append(text)
        logging.getLogger("ui").info(text)

    def _on_action_received(self, action: str) -> None:
        self._last_action.setText(f"动作回显：{action}")
        self._append_log(f"收到 CONTROL_ACTION={action}")

    def _on_teleop_velocity(self, lx: float, ly: float, az: float) -> None:
        self._worker.publish_velocity(lx, ly, az)

    def _on_teleop_stop(self) -> None:
        self._worker.publish_stop(repeat=3)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        # Refuse close while Jetson SSH / QThread remote ops are in flight.
        if self._remote_busy:
            event.ignore()
            self._append_log("远程定位/雷达操作进行中，请等待完成后再关闭")
            return
        for worker in (
            self._l1_stack_worker,
            self._l1_lio_worker,
            self._lidar_worker,
            self._rviz_precheck_worker,
            self._lio_rviz_precheck_worker,
            self._env_worker,
            self._topic_worker,
        ):
            if worker is not None and worker.isRunning():
                event.ignore()
                self._append_log("后台线程仍在运行，请稍后再关闭")
                return

        self._closing = True
        self._teleop_panel.stop()
        self._worker.publish_stop(repeat=3)
        self._worker.stop()
        self._worker.wait(1500)
        if self._rviz_mgr.running:
            self._close_local_rviz()
        super().closeEvent(event)
