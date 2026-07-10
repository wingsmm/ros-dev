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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import CockpitConfig, app_root
from core.ros2_lidar_probe import (
    format_lidar_summary,
    format_lio_summary,
    probe_lidar_status,
    probe_lio_status,
)
from core.ros2_probe import (
    env_check_report,
    format_topic_report,
    format_topic_summary,
    probe_key_topics,
    ros2_node_list,
)
from core.ros2_control import Ros2ControlWorker
from core.rviz_process import RvizProcessManager, rviz2_start_command
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
            )
            lio = probe_lio_status(
                self._cfg.lio_odom_topic,
                self._cfg.lio_path_topic,
                self._cfg.lio_cloud_registered_topic,
                root,
            )
            self.finished_status.emit(raw, lio)
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
        self._lidar_summary_line = ""
        self._lidar_summary_ok = True
        self._rviz_label = ""

        self._build_ui()
        self._wire()
        self._update_lidar_rviz_path_label()
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
        self._lidar_panel.mode_group.buttonClicked.connect(
            lambda _button: self._update_lidar_rviz_path_label()
        )
        self._lidar_panel.btn_start_rviz.clicked.connect(self._start_lidar_rviz)
        self._lidar_panel.btn_stop_rviz.clicked.connect(self._stop_lidar_rviz)
        self._lidar_panel.btn_diag_refresh.clicked.connect(self._refresh_lidar_status)

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
    def _one_line_lidar_summary(status, lio_status, mode: str, rviz_label: str = "") -> tuple[str, bool]:
        cloud = "%.1fHz" % status.cloud_hz if status.cloud_hz else "cloud无"
        imu = "%.0fHz" % status.imu_hz if status.imu_hz else "imu无"
        tf = "OK" if status.tf_ok else "missing"
        parts = ["cloud %s" % cloud, "imu %s" % imu, "TF %s" % tf]
        if rviz_label:
            parts.append("RViz:%s" % rviz_label)
        if mode == LidarPanel.MODE_LIO:
            parts.append("LIO:%s" % ("运行" if "running" in lio_status.jetson_lio else "停"))

        if mode == LidarPanel.MODE_BASE:
            ok = status.cloud_ok and status.tf_ok
        elif mode == LidarPanel.MODE_RAW:
            ok = status.cloud_ok
        else:
            ok = status.cloud_ok
        return " · ".join(parts), ok

    def _update_lidar_summary_display(self, rviz_extra: str = "") -> None:
        text = self._lidar_summary_line + rviz_extra
        self._lidar_panel.set_summary(text, self._lidar_summary_ok)

    def _on_lidar_status_done(self, status, lio_status) -> None:
        rviz_label = self._rviz_label if self._rviz_mgr.running else ""
        self._lidar_summary_line, self._lidar_summary_ok = (
            self._one_line_lidar_summary(
                status,
                lio_status,
                self._lidar_panel.selected_mode(),
                rviz_label,
            )
        )
        self._update_lidar_summary_display()

        diag = (
            "[原始]\n"
            + format_lidar_summary(status)
            + "\n\n[LIO]\n"
            + format_lio_summary(lio_status)
        )
        if status.detail and status.detail != "OK":
            diag += "\n\n[原始详情] " + status.detail
        if lio_status.detail and lio_status.detail != "OK":
            diag += "\n[LIO详情] " + lio_status.detail
        self._lidar_panel.set_diag_detail(diag)

        if not self._lidar_summary_ok:
            self._append_log("雷达诊断：%s" % status.detail)

    def _on_lidar_status_failed(self, text: str) -> None:
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
            self._append_log("已打开 %s" % label)

    def _selected_lidar_rviz(self):
        mode = self._lidar_panel.selected_mode()
        if mode == LidarPanel.MODE_RAW:
            return self._cfg.rviz_config, "原始点云"
        if mode == LidarPanel.MODE_BASE:
            return self._cfg.lidar_base_rviz, "车体对齐"
        return self._cfg.lidar_mapping_rviz, "雷达/里程计"

    def _update_lidar_rviz_path_label(self) -> None:
        cfg_path, _label = self._selected_lidar_rviz()
        self._lidar_panel.set_config_path(str(cfg_path))

    def _start_lidar_rviz(self) -> None:
        cfg_path, label = self._selected_lidar_rviz()
        self._open_rviz(cfg_path, label)

    def _stop_lidar_rviz(self) -> None:
        self._rviz_mgr.stop()
        stop_script = app_root() / "scripts" / "stop_unilidar_rviz.sh"
        if stop_script.is_file():
            subprocess.run(["bash", str(stop_script)], check=False)
        self._append_log("已关闭 RViz")
        self._rviz_label = ""

    def _on_rviz_running_changed(self, running: bool) -> None:
        if self._lidar_summary_line:
            self._refresh_lidar_status()
        elif running:
            self._lidar_panel.set_summary(
                "RViz 运行中" + (":%s" % self._rviz_label if self._rviz_label else ""),
                True,
            )
        else:
            self._lidar_panel.set_summary("RViz 未启动", True)

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
        self._teleop_panel.stop()
        self._worker.publish_stop(repeat=3)
        self._worker.stop()
        self._worker.wait(1500)
        if self._rviz_mgr.running:
            self._stop_lidar_rviz()
        super().closeEvent(event)
