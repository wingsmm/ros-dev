from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, QMetaObject, Q_ARG

from core.app_shutdown import register_shutdown
from core.camera_mjpeg_url import resolve_mjpeg_url_for_robot
from core.camera_ros2_bridge_worker import (
    CameraBridgeRuntimeStatus,
    CameraRos2BridgeWorker,
)
from core.camera_topic_probe import CameraTopicProbeResult, format_probe_summary
from core.camera_topic_probe_worker import CameraTopicProbeWorker
from core.camera_topics import CAMERA_DIAGNOSTIC_TOPICS
from core.ros2_runtime import (
    Ros2RuntimeError,
    Ros2RuntimeStatus,
    camera_diagnostic_shell_commands,
    require_ros2_bridge,
    require_ros2_rviz,
    ros2_status,
    rviz_rgbd_camera_config_path,
)
from core.rviz_process_manager import RvizProcessManager

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo

logger = logging.getLogger(__name__)


@dataclass
class CameraRos2PanelSnapshot:
    env: Ros2RuntimeStatus = field(default_factory=ros2_status)
    bridge_running: bool = False
    bridge_status: CameraBridgeRuntimeStatus = field(
        default_factory=CameraBridgeRuntimeStatus
    )
    topic_probe: str = ""
    topic_probe_result: Optional[CameraTopicProbeResult] = None
    mjpeg_url: str = ""
    rviz_running: bool = False
    rviz_error: str = ""
    diagnostics_expanded: bool = False


class CameraRos2BridgeManager(QObject):
    """Camera module: MJPEG bridge + RGB-D topic probe + RViz2 (Phase 1)."""

    snapshot_updated = pyqtSignal(object)
    action_message = pyqtSignal(str)

    def __init__(self, robot: Optional["RobotInfo"] = None, parent=None) -> None:
        super().__init__(parent)
        self._robot = robot
        self._thread: Optional[QThread] = None
        self._worker: Optional[CameraRos2BridgeWorker] = None
        self._probe_thread: Optional[QThread] = None
        self._probe_worker: Optional[CameraTopicProbeWorker] = None
        self._rviz = RvizProcessManager()
        self._bridge_status = CameraBridgeRuntimeStatus()
        self._topic_probe = ""
        self._topic_probe_result: Optional[CameraTopicProbeResult] = None
        self._diagnostics_expanded = False
        self._shutdown_done = False
        register_shutdown(self.shutdown, name="camera_ros2_bridge_manager", priority=25)

    def set_robot(self, robot: Optional["RobotInfo"]) -> None:
        self._robot = robot

    def set_diagnostics_expanded(self, expanded: bool) -> None:
        self._diagnostics_expanded = expanded
        if expanded:
            self._ensure_probe_worker()
            if self._probe_worker is not None:
                QMetaObject.invokeMethod(
                    self._probe_worker,
                    "start_polling",
                    Qt.QueuedConnection,
                )
        elif self._probe_worker is not None:
            QMetaObject.invokeMethod(
                self._probe_worker,
                "stop_polling",
                Qt.QueuedConnection,
            )

    def _emit_action_message(self, text: str) -> None:
        try:
            self.action_message.emit(text)
        except RuntimeError:
            logger.debug("skip action_message after QObject deleted: %s", text)

    def _emit_snapshot(self) -> None:
        try:
            self.snapshot_updated.emit(self.snapshot())
        except RuntimeError:
            logger.debug("skip snapshot_updated after QObject deleted")

    def start_bridge(self) -> bool:
        try:
            require_ros2_bridge()
        except Ros2RuntimeError as exc:
            self._emit_action_message(str(exc))
            self._emit_snapshot()
            return False
        if self._thread is not None:
            if self._bridge_status.running:
                self._emit_action_message("Camera Bridge 已在运行")
                return True
            self.stop_bridge()
        self._thread = QThread(self)
        self._worker = CameraRos2BridgeWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._on_thread_started)
        self._worker.status_updated.connect(self._on_bridge_status)
        self._worker.bridge_failed.connect(self._on_bridge_failed)
        self._thread.start()
        self._emit_action_message("正在启动 Camera Bridge…")
        return True

    def stop_bridge(self) -> None:
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker,
                "stop_bridge",
                Qt.BlockingQueuedConnection,
            )
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(4000)
        self._worker = None
        self._thread = None
        self._bridge_status = CameraBridgeRuntimeStatus()
        self._emit_action_message("Camera Bridge 已停止")
        self._emit_snapshot()

    def start_rviz(self) -> bool:
        try:
            require_ros2_rviz()
        except Ros2RuntimeError as exc:
            self._emit_action_message(str(exc))
            self._emit_snapshot()
            return False
        if not self._rviz.start(rviz_rgbd_camera_config_path()):
            self._emit_action_message(self._rviz.last_error or "RViz2 启动失败")
            self._emit_snapshot()
            return False
        self._emit_action_message("RViz2 已启动（RGB-D 配置）")
        self._emit_snapshot()
        return True

    def stop_rviz(self) -> None:
        self._rviz.stop()
        self._emit_action_message("RViz2 已停止")
        self._emit_snapshot()

    def _on_thread_started(self) -> None:
        if self._worker is None:
            return
        url = resolve_mjpeg_url_for_robot(self._robot) if self._robot else ""
        QMetaObject.invokeMethod(
            self._worker,
            "set_mjpeg_url",
            Qt.BlockingQueuedConnection,
            Q_ARG(str, url),
        )
        QMetaObject.invokeMethod(
            self._worker,
            "start_bridge",
            Qt.BlockingQueuedConnection,
        )

    def refresh_topic_status(self) -> None:
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker,
                "reset_rate_window",
                Qt.QueuedConnection,
            )
        self._ensure_probe_worker()
        if self._probe_worker is not None:
            QMetaObject.invokeMethod(
                self._probe_worker,
                "probe_now",
                Qt.QueuedConnection,
            )
        else:
            self._topic_probe = "topic 探测线程未就绪"
            self._emit_snapshot()

    def diagnostic_commands(self) -> str:
        return camera_diagnostic_shell_commands()

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("shutting down camera ROS2 bridge manager")
        self.stop_rviz()
        self._stop_probe_worker()
        self.stop_bridge()

    def snapshot(self) -> CameraRos2PanelSnapshot:
        bridge_running = self._thread is not None or self._bridge_status.running
        url = resolve_mjpeg_url_for_robot(self._robot) if self._robot else ""
        return CameraRos2PanelSnapshot(
            env=ros2_status(),
            bridge_running=bridge_running,
            bridge_status=self._bridge_status,
            topic_probe=self._topic_probe,
            topic_probe_result=self._topic_probe_result,
            mjpeg_url=url,
            rviz_running=self._rviz.is_running(),
            rviz_error=self._rviz.last_error,
            diagnostics_expanded=self._diagnostics_expanded,
        )

    def _ensure_probe_worker(self) -> None:
        if self._probe_thread is not None:
            return
        self._probe_thread = QThread(self)
        self._probe_worker = CameraTopicProbeWorker()
        self._probe_worker.moveToThread(self._probe_thread)
        self._probe_worker.result_ready.connect(self._on_probe_result)
        self._probe_thread.start()

    def _stop_probe_worker(self) -> None:
        if self._probe_worker is not None:
            QMetaObject.invokeMethod(
                self._probe_worker,
                "stop_polling",
                Qt.BlockingQueuedConnection,
            )
        if self._probe_thread is not None:
            self._probe_thread.quit()
            self._probe_thread.wait(3000)
        self._probe_worker = None
        self._probe_thread = None

    def _on_probe_result(self, result: object) -> None:
        if not isinstance(result, CameraTopicProbeResult):
            return
        self._topic_probe_result = result
        self._topic_probe = format_probe_summary(
            result, topics=CAMERA_DIAGNOSTIC_TOPICS
        )
        self._emit_snapshot()

    def _on_bridge_status(self, status: object) -> None:
        if isinstance(status, CameraBridgeRuntimeStatus):
            self._bridge_status = status
        self._emit_snapshot()

    def _on_bridge_failed(self, detail: str) -> None:
        logger.error("camera ROS2 bridge failed: %s", detail)
        self._bridge_status = CameraBridgeRuntimeStatus(
            running=False, last_error=detail
        )
        self._emit_action_message(detail)
        self._emit_snapshot()
