"""Jetson Qt cockpit for the dry-run /cmd_vel bridge."""

from __future__ import annotations

import logging
import os

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox,
    QLabel,
    QMainWindow,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config import CockpitConfig
from core.ros2_probe import (
    env_check_report,
    format_topic_report,
    format_topic_summary,
    probe_key_topics,
    ros2_node_list,
)
from core.ros2_control import Ros2ControlWorker
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


class MainWindow(QMainWindow):
    def __init__(self, cfg: CockpitConfig, log_path) -> None:
        super().__init__()
        self.setWindowTitle("Jetson Qt 控制台 - /cmd_vel 干跑")
        self.resize(720, 480)
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
        super().closeEvent(event)
