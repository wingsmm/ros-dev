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
from core.ros2_runtime import (
    Ros2RuntimeError,
    Ros2RuntimeStatus,
    camera_diagnostic_shell_commands,
    require_ros2_bridge,
    ros2_status,
)

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
    mjpeg_url: str = ""


class CameraRos2BridgeManager(QObject):
    """Camera page: MJPEG -> ROS2 /camera/image_raw (no RViz2; WSL2 OpenGL unsupported)."""

    snapshot_updated = pyqtSignal(object)
    action_message = pyqtSignal(str)

    def __init__(self, robot: Optional["RobotInfo"] = None, parent=None) -> None:
        super().__init__(parent)
        self._robot = robot
        self._thread: Optional[QThread] = None
        self._worker: Optional[CameraRos2BridgeWorker] = None
        self._bridge_status = CameraBridgeRuntimeStatus()
        self._topic_probe = ""
        self._shutdown_done = False
        register_shutdown(self.shutdown, name="camera_ros2_bridge_manager", priority=25)

    def set_robot(self, robot: Optional["RobotInfo"]) -> None:
        self._robot = robot

    def start_bridge(self) -> bool:
        try:
            require_ros2_bridge()
        except Ros2RuntimeError as exc:
            self.action_message.emit(str(exc))
            self._emit_snapshot()
            return False
        if self._thread is not None:
            if self._bridge_status.running:
                self.action_message.emit("Camera Bridge 已在运行")
                return True
            self.stop_bridge()
        self._thread = QThread(self)
        self._worker = CameraRos2BridgeWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._on_thread_started)
        self._worker.status_updated.connect(self._on_bridge_status)
        self._worker.bridge_failed.connect(self._on_bridge_failed)
        self._thread.start()
        self.action_message.emit("正在启动 Camera Bridge…")
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
        self.action_message.emit("Camera Bridge 已停止")
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
        self._topic_probe = "内部计数已刷新；可用「复制诊断命令」核对 topic"
        self._emit_snapshot()

    def diagnostic_commands(self) -> str:
        return camera_diagnostic_shell_commands()

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("shutting down camera ROS2 bridge manager")
        self.stop_bridge()

    def snapshot(self) -> CameraRos2PanelSnapshot:
        bridge_running = self._thread is not None or self._bridge_status.running
        url = resolve_mjpeg_url_for_robot(self._robot) if self._robot else ""
        return CameraRos2PanelSnapshot(
            env=ros2_status(),
            bridge_running=bridge_running,
            bridge_status=self._bridge_status,
            topic_probe=self._topic_probe,
            mjpeg_url=url,
        )

    def _on_bridge_status(self, status: object) -> None:
        if isinstance(status, CameraBridgeRuntimeStatus):
            self._bridge_status = status
        self._emit_snapshot()

    def _on_bridge_failed(self, detail: str) -> None:
        logger.error("camera ROS2 bridge failed: %s", detail)
        self._bridge_status = CameraBridgeRuntimeStatus(
            running=False, last_error=detail
        )
        self.action_message.emit(detail)
        self._emit_snapshot()

    def _emit_snapshot(self) -> None:
        self.snapshot_updated.emit(self.snapshot())
