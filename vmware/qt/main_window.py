import logging
import sys
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from core.env import load_config, summarize_prereqs
from core.logging_config import log_ui_line
from core.process_manager import ProcessManager
from core.rviz_process import RvizProcessManager
from core.ros1_probe import (
    cmd_vel_subscriber_ok,
    depth_diagnostics,
    env_check_report,
    format_topic_table,
    KEY_TOPICS,
    master_reachable,
    probe_enhanced_local_topics,
    probe_topics,
    tf_transform_exists,
)
from core.rviz_commands import DEPTH_ENHANCED_MODE, IMAGE_VIEW_MODES, RvizCommands
from core.teleop_publisher import TeleopPublisher
from core.ui_log_handler import UiLogHandler, UiLogSignaler
from ui.log_panel import LogPanel
from ui.rviz_panel import RvizPanel
from ui.status_panel import StatusPanel
from ui.teleop_panel import TeleopPanel
from ui.topic_panel import TopicPanel

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ProbeWorker(QThread):
    finished_result = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, fn):
        super(ProbeWorker, self).__init__()
        self.fn = fn

    def run(self):
        try:
            detail_text, summary_text = self.fn()
            self.finished_result.emit(detail_text, summary_text)
        except Exception as exc:
            self.failed.emit(str(exc))


class EnvCheckWorker(QThread):
    finished_text = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, cfg):
        super(EnvCheckWorker, self).__init__()
        self.cfg = cfg

    def run(self):
        try:
            self.finished_text.emit(env_check_report(self.cfg))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, log_settings=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle("VMware Qt RViz 控制台 (v1)")
        self.resize(920, 720)
        self._log_settings = log_settings

        self._ui_log_signaler = UiLogSignaler(self)
        self._ui_log_handler = UiLogHandler(self._ui_log_signaler)
        logging.getLogger("ui").addHandler(self._ui_log_handler)
        self._ui_log_signaler.line.connect(self._append_log_line)

        self.cfg = load_config()
        self.rviz = RvizCommands(self.cfg)
        self.teleop = TeleopPublisher(self.cfg)
        self.rviz_proc = RvizProcessManager(self)
        self.rviz_proc.output.connect(self._log)
        self.rviz_proc.running_changed.connect(self._on_rviz_running_changed)
        self.depth_view_proc = RvizProcessManager(self)
        self.depth_view_proc.output.connect(self._log)
        self.rgb_view_proc = RvizProcessManager(self)
        self.rgb_view_proc.output.connect(self._log)
        self.preview_view_proc = RvizProcessManager(self)
        self.preview_view_proc.output.connect(self._log)
        self.depth_cloud_proc = RvizProcessManager(self)
        self.depth_cloud_proc.output.connect(self._log)
        self.camera_base_tf_proc = RvizProcessManager(self)
        self.camera_base_tf_proc.output.connect(self._log)
        self.camera_optical_tf_proc = RvizProcessManager(self)
        self.camera_optical_tf_proc.output.connect(self._log)
        self.proc = ProcessManager()
        self.proc.output.connect(self._log)
        self.proc.busy_changed.connect(self._on_busy)
        self._probe_worker = None
        self._env_worker = None

        self.status_panel = StatusPanel()
        self.rviz_panel = RvizPanel(list(self.cfg.rviz_configs.keys()))
        self.teleop_panel = TeleopPanel(
            linear_speed=self.cfg.teleop_linear_speed,
            angular_speed=self.cfg.teleop_angular_speed,
            repeat_hz=self.cfg.teleop_repeat_hz,
        )
        self.topic_panel = TopicPanel()

        self.log_panel = LogPanel()

        hint = QLabel(
            "纯客户端：小车手动 pc_stack；本 VM 连接 Master、检查 topic、本地 RViz。"
            "不 SSH，不远程启脚本。"
        )
        hint.setWordWrap(True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(hint)
        layout.addWidget(self.status_panel)
        layout.addWidget(self.rviz_panel)
        layout.addWidget(self.teleop_panel)
        layout.addWidget(self.topic_panel)
        layout.addWidget(QLabel("日志"))
        layout.addWidget(self.log_panel)
        self.setCentralWidget(central)

        self._wire()
        self._refresh_static()
        self._update_rviz_path_label()
        self._update_rviz_buttons()
        self._update_teleop_state()
        self._log_prereqs()

    def _wire(self):
        self.status_panel.btn_refresh.clicked.connect(self._refresh_static)
        self.status_panel.btn_check_env.clicked.connect(self._run_env_check)
        self.rviz_panel.group.buttonClicked.connect(lambda _: self._update_rviz_path_label())
        self.rviz_panel.btn_start.clicked.connect(self._start_rviz)
        self.rviz_panel.btn_stop.clicked.connect(self._stop_rviz)
        self.topic_panel.btn_probe.clicked.connect(self._probe_topics)
        self.topic_panel.btn_depth.clicked.connect(self._probe_depth)
        self.teleop_panel.velocity_requested.connect(self._on_teleop_velocity)
        self.teleop_panel.stop_requested.connect(self._on_teleop_stop)

    def closeEvent(self, event):
        self.teleop_panel.stop()
        self.teleop.shutdown()
        if self.rviz_proc.running:
            self._stop_rviz()
        super(MainWindow, self).closeEvent(event)

    def _append_log_line(self, line):
        self.log_panel.append(line)

    def _log(self, text):
        log_ui_line(text)

    def _log_prereqs(self):
        if self._log_settings is not None:
            self._log("日志目录: %s" % self._log_settings.log_dir)
        for line in summarize_prereqs(self.cfg):
            self._log(line)

    def _on_busy(self, busy):
        for btn in (
            self.status_panel.btn_refresh,
            self.status_panel.btn_check_env,
            self.topic_panel.btn_probe,
            self.topic_panel.btn_depth,
        ):
            btn.setEnabled(not busy)
        self._update_rviz_buttons()

    def _update_rviz_buttons(self):
        running = self.rviz_proc.running
        self.rviz_panel.btn_start.setEnabled(not running and not self.proc.busy)
        self.rviz_panel.btn_stop.setEnabled(running and not self.proc.busy)

    def _selected_rviz_path(self):
        label = self.rviz_panel.selected_label()
        return self.cfg.rviz_configs.get(label)

    def _update_rviz_path_label(self):
        path = self._selected_rviz_path()
        if path is None:
            self.rviz_panel.set_config_path("-")
            return
        self.rviz_panel.set_config_path(str(path))

    def _refresh_static(self):
        self.cfg = load_config()
        self.rviz = RvizCommands(self.cfg)
        self.teleop.cfg = self.cfg
        self.teleop_panel.set_speeds(
            self.cfg.teleop_linear_speed,
            self.cfg.teleop_angular_speed,
        )
        self.status_panel.set_master_uri(self.cfg.ros_master_uri)
        self.status_panel.set_ros_ip(self.cfg.ros_ip)
        self.status_panel.set_master_ok(master_reachable(self.cfg))
        self._update_rviz_status_label()
        self._update_teleop_state()

    def _update_teleop_state(self):
        if not self.teleop.is_available:
            self.teleop_panel.set_controls_enabled(
                False,
                "python2 不可用：请在 VM 安装 ROS Melodic 后使用 ./run.sh 启动",
            )
            return
        if not master_reachable(self.cfg):
            self.teleop_panel.set_controls_enabled(
                False,
                "Master 不可达：遥控已禁用。小车需 radar2d-start / full-start。",
            )
            return
        ok, detail = cmd_vel_subscriber_ok(self.cfg, self.cfg.cmd_vel_topic)
        if not ok:
            self.teleop_panel.set_controls_enabled(
                False,
                detail,
            )
            return
        self.teleop_panel.set_controls_enabled(True)
        self.teleop_panel.set_keyboard_enabled(self.cfg.teleop_enable_keyboard)

    def _on_teleop_velocity(self, lx, ly, az):
        ok, err = self.teleop.publish_velocity(lx, ly, az)
        if not ok:
            self._log("[ERR] 遥控发布失败: %s" % err)
            self.teleop_panel.set_controls_enabled(
                False,
                "遥控发布失败: %s" % err,
            )

    def _on_teleop_stop(self):
        self.teleop.stop(repeat=3)

    def _update_rviz_status_label(self):
        if self.rviz_proc.running:
            self.status_panel.set_rviz_hint(True, self.rviz_proc.pid)
        else:
            self.status_panel.set_rviz_hint(False, 0)

    def _on_rviz_running_changed(self, _running):
        self._update_rviz_status_label()
        self._update_rviz_buttons()

    def _run_env_check(self):
        if self._env_worker and self._env_worker.isRunning():
            self._log("[WARN] 环境检查仍在进行")
            return
        self._log("--- 检查环境 ---")
        self._env_worker = EnvCheckWorker(self.cfg)
        self._env_worker.finished_text.connect(self._on_env_check_done)
        self._env_worker.failed.connect(self._on_env_check_failed)
        self._env_worker.start()

    def _on_env_check_done(self, text):
        self._log(text)
        self._refresh_static()
        ok, detail = cmd_vel_subscriber_ok(self.cfg, self.cfg.cmd_vel_topic)
        self._log(
            "[OK] %s" % detail if ok else "[WARN] %s" % detail
        )

    def _on_env_check_failed(self, message):
        self._log("[ERR] 环境检查失败: %s" % message)

    def _start_rviz(self):
        path = self._selected_rviz_path()
        label = self.rviz_panel.selected_label()
        if path is None or not path.is_file():
            QMessageBox.warning(self, "RViz 配置缺失", "所选 rviz 文件不存在:\n%s" % path)
            return
        if not master_reachable(self.cfg):
            hint = (
                "请在小车手动启动 pc_stack camera-deep-start，并确认 ROS_MASTER_URI。"
                if label == DEPTH_ENHANCED_MODE
                else "请在小车手动启动 pc_stack（camera-start 或 full-start），并确认 ROS_MASTER_URI。"
            )
            QMessageBox.warning(self, "Master 不可达", hint)
            return
        if self.rviz_proc.running:
            QMessageBox.information(self, "RViz", "本客户端 RViz 已在运行。")
            return
        cmd = self.rviz.start_command(path)
        if not self.rviz_proc.start(
            cmd,
            config_path=str(path),
            process_label="RViz",
            log_prefix="rviz",
        ):
            return
        if label in IMAGE_VIEW_MODES:
            self._start_rgb_depth_image_views(label)
            if label == DEPTH_ENHANCED_MODE:
                self._start_depth_enhanced_extras()

    def _start_rgb_depth_image_views(self, reason):
        self._log("[INFO] %s：打开 RGB + 深度 image_view 窗口" % reason)
        self.rgb_view_proc.start(
            self.rviz.rgb_image_view_command(),
            config_path="image_view-rgb",
            process_label="image_view RGB",
            log_prefix="image_view_rgb",
        )
        self.depth_view_proc.start(
            self.rviz.depth_image_view_command(),
            config_path="image_view-depth",
            process_label="image_view Depth",
            log_prefix="image_view_depth",
        )

    def _start_depth_enhanced_extras(self):
        self._log("[INFO] 深度增强：相机 TF + preview + VM 本地点云")
        self._start_depth_enhanced_camera_tf()
        self.preview_view_proc.start(
            self.rviz.preview_image_view_command(),
            config_path="image_view-preview",
            process_label="image_view Preview",
            log_prefix="image_view_preview",
        )
        self.depth_cloud_proc.start(
            self.rviz.depth_point_cloud_command(),
            config_path="depth-point-cloud",
            process_label="depth point cloud",
            log_prefix="depth_point_cloud",
        )

    def _start_depth_enhanced_camera_tf(self):
        if not self.cfg.camera_tf_enable:
            self._log("[INFO] CAMERA_TF_ENABLE=0，跳过 VM 相机 static TF")
            return
        base = self.cfg.robot_base_frame
        cam = self.cfg.camera_frame
        optical = self.cfg.camera_optical_frame
        if tf_transform_exists(self.cfg, base, cam):
            self._log(
                "[INFO] TF %s -> %s 已存在，跳过 VM base 外参发布"
                % (base, cam)
            )
        else:
            self._log(
                "[INFO] 启动 VM static TF: %s -> %s (借鉴 pc-client 外参)"
                % (base, cam)
            )
            self.camera_base_tf_proc.start(
                self.rviz.camera_base_tf_command(),
                config_path="camera-base-tf",
                process_label="camera base TF",
                log_prefix="camera_base_tf",
            )
        if tf_transform_exists(self.cfg, cam, optical):
            self._log(
                "[INFO] TF %s -> %s 已存在，跳过 VM optical TF"
                % (cam, optical)
            )
        else:
            self._log("[INFO] 启动 VM static TF: %s -> %s" % (cam, optical))
            self.camera_optical_tf_proc.start(
                self.rviz.camera_optical_tf_command(),
                config_path="camera-optical-tf",
                process_label="camera optical TF",
                log_prefix="camera_optical_tf",
            )

    def _stop_rviz(self):
        if not self.rviz_proc.running:
            self._log("[INFO] 本客户端未启动 RViz")
            return
        self.preview_view_proc.stop()
        self.rgb_view_proc.stop()
        self.depth_view_proc.stop()
        self.depth_cloud_proc.stop()
        self.camera_optical_tf_proc.stop()
        self.camera_base_tf_proc.stop()
        self.rviz_proc.stop()

    def _probe_topics(self):
        def fn():
            rows = probe_topics(self.cfg)
            text = format_topic_table(rows)
            ok = sum(1 for row in rows if row.has_publisher)
            summary = "关键 topic: %s/%s 有 publisher" % (ok, len(KEY_TOPICS))
            label = self.rviz_panel.selected_label()
            if label == DEPTH_ENHANCED_MODE:
                local_rows = probe_enhanced_local_topics(self.cfg)
                text += (
                    "\n--- VM 本地点云（深度增强启动 RViz 后才有）---\n"
                    + format_topic_table(local_rows)
                )
                local_ok = sum(1 for row in local_rows if row.has_publisher)
                summary += "；本地点云 %s/%s" % (local_ok, len(local_rows))
            return text, summary

        self._run_probe(fn)

    def _probe_depth(self):
        def fn():
            result = depth_diagnostics(self.cfg)
            summary = "深度: pub=%s frame=%s hz=%s" % (
                result.depth_has_pub,
                result.depth_frame_ok,
                result.depth_hz or "-",
            )
            return "\n".join(result.lines), summary

        self._run_probe(fn)

    def _run_probe(self, fn):
        if self._probe_worker and self._probe_worker.isRunning():
            self._log("[WARN] 诊断仍在进行")
            return

        self.topic_panel.set_detail("运行中...")
        self._probe_worker = ProbeWorker(fn)
        self._probe_worker.finished_result.connect(self._on_probe_done)
        self._probe_worker.failed.connect(self._on_probe_failed)
        self._probe_worker.start()

    def _on_probe_done(self, detail_text, summary_text):
        self.topic_panel.set_detail(detail_text)
        if summary_text:
            self.topic_panel.set_summary(summary_text)
        self._refresh_static()

    def _on_probe_failed(self, message):
        self.topic_panel.set_detail("[ERR] %s" % message)
