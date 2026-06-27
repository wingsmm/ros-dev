from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, QMetaObject, Q_ARG

from core.app_shutdown import register_shutdown
from core.camera_mjpeg_url import resolve_mjpeg_url_for_robot
from core.camera_topic_probe import CameraTopicProbeResult, format_probe_summary
from core.camera_topic_probe_worker import CameraTopicProbeWorker
from core.camera_topics import CAMERA_DIAGNOSTIC_TOPICS
from core.latest_frame_mailbox import DepthBridgeFrame, LatestFrameMailbox
from core.odom_session_origin import ORIGIN_POLICY_LABEL
from core.ros2_bridge_worker import BridgeRuntimeStatus, Ros2BridgeWorker
from core.ros2_runtime import (
    Ros2RuntimeError,
    Ros2RuntimeStatus,
    camera_diagnostic_shell_commands,
    diagnostic_shell_commands,
    require_ros2_bridge,
    require_ros2_rviz,
    ros2_status,
    rviz_rgbd_camera_config_path,
    rviz_robot_config_path,
)
from core.rviz_process_manager import RvizProcessManager

if TYPE_CHECKING:
    from core.robot_session import RobotSession
    from ui.models.robot_info import RobotInfo
    from ui.widgets.mjpeg_stream import MjpegStreamController

logger = logging.getLogger(__name__)


@dataclass
class Ros2RvizPanelSnapshot:
    env: Ros2RuntimeStatus = field(default_factory=ros2_status)
    bridge_running: bool = False
    bridge_status: BridgeRuntimeStatus = field(default_factory=BridgeRuntimeStatus)
    json_connected: bool = False
    rviz_running: bool = False
    rviz_error: str = ""
    topic_probe: str = ""
    origin_policy: str = ""
    origin_summary: str = ""


@dataclass
class CameraRos2PanelSnapshot:
    env: Ros2RuntimeStatus = field(default_factory=ros2_status)
    bridge_running: bool = False
    bridge_status: BridgeRuntimeStatus = field(default_factory=BridgeRuntimeStatus)
    topic_probe: str = ""
    topic_probe_result: Optional[CameraTopicProbeResult] = None
    mjpeg_url: str = ""
    rviz_running: bool = False
    rviz_error: str = ""
    diagnostics_expanded: bool = False


class Ros2BridgeManager(QObject):
    """Global ROS2 bridge: JSON telemetry + RGB/Depth ingress tee -> xtark_ros2_bridge."""

    snapshot_updated = pyqtSignal(object)
    action_message = pyqtSignal(str)

    def __init__(
        self,
        session: Optional["RobotSession"] = None,
        robot: Optional["RobotInfo"] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._robot = robot
        self._thread: Optional[QThread] = None
        self._worker: Optional[Ros2BridgeWorker] = None
        self._rviz = RvizProcessManager()
        self._bridge_status = BridgeRuntimeStatus()
        self._topic_probe = ""
        self._session_slots: list[tuple[object, object]] = []
        self._probe_thread: Optional[QThread] = None
        self._probe_worker: Optional[CameraTopicProbeWorker] = None
        self._topic_probe_result: Optional[CameraTopicProbeResult] = None
        self._camera_topic_probe = ""
        self._diagnostics_expanded = False
        self._rgb_mailbox: LatestFrameMailbox[bytes] = LatestFrameMailbox()
        self._depth_mailbox: LatestFrameMailbox[DepthBridgeFrame] = LatestFrameMailbox()
        self._rgb_tee_enabled = False
        self._depth_tee_enabled = False
        self._rgb_stream: Optional["MjpegStreamController"] = None
        self._shutdown_done = False
        register_shutdown(self.shutdown, name="ros2_bridge_manager", priority=20)

    def set_session(self, session: Optional["RobotSession"]) -> None:
        if self._session is session:
            return
        self._disconnect_session()
        self._session = session
        if self._worker is not None and session is not None:
            self._connect_session(session)

    def set_robot(self, robot: Optional["RobotInfo"]) -> None:
        self._robot = robot

    def register_rgb_stream(self, stream: Optional["MjpegStreamController"]) -> None:
        if self._rgb_stream is stream:
            return
        if self._rgb_stream is not None:
            try:
                self._rgb_stream.bridge_jpeg.disconnect(self._tee_rgb_jpeg)
            except TypeError:
                pass
        self._rgb_stream = stream
        if stream is not None:
            stream.bridge_jpeg.connect(self._tee_rgb_jpeg, Qt.QueuedConnection)

    def set_rgb_bridge_enabled(self, enabled: bool) -> None:
        self._rgb_tee_enabled = enabled

    def set_depth_bridge_enabled(self, enabled: bool) -> None:
        self._depth_tee_enabled = enabled

    def set_camera_diagnostics_expanded(self, expanded: bool) -> None:
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

    def start_bridge(self) -> bool:
        return self._ensure_bridge_started()

    def _ensure_bridge_started(self) -> bool:
        try:
            require_ros2_bridge()
        except Ros2RuntimeError as exc:
            self._emit_action_message(str(exc))
            self._emit_snapshot()
            return False
        if self._thread is not None:
            if self._bridge_status.running:
                return True
            self.stop_bridge()
        self._disconnect_session()
        self._thread = QThread(self)
        self._worker = Ros2BridgeWorker()
        self._worker.bind_mailboxes(self._rgb_mailbox, self._depth_mailbox)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start_bridge)
        self._worker.status_updated.connect(self._on_bridge_status)
        self._worker.bridge_failed.connect(self._on_bridge_failed)
        self._thread.start()
        if self._session is not None:
            self._connect_session(self._session)
            self._replay_session_cache(self._session)
        self._emit_action_message("正在启动 ROS2 Bridge…")
        return True

    def stop_bridge(self) -> None:
        self._disconnect_session()
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
        self._bridge_status = BridgeRuntimeStatus()
        self._emit_action_message("ROS2 Bridge 已停止")
        self._emit_snapshot()

    def start_rviz(self, config: Optional[Path] = None) -> bool:
        try:
            require_ros2_rviz()
        except Ros2RuntimeError as exc:
            self._emit_action_message(str(exc))
            self._emit_snapshot()
            return False
        rviz_config = config or rviz_robot_config_path()
        if not self._rviz.start(rviz_config):
            self._emit_action_message(self._rviz.last_error or "RViz2 启动失败")
            self._emit_snapshot()
            return False
        self._emit_action_message(f"RViz2 已启动（{rviz_config.name}）")
        self._emit_snapshot()
        return True

    def start_robot_rviz(self) -> bool:
        return self.start_rviz(rviz_robot_config_path())

    def start_camera_rviz(self) -> bool:
        return self.start_rviz(rviz_rgbd_camera_config_path())

    def stop_rviz(self) -> None:
        self._rviz.stop()
        self._emit_action_message("RViz2 已停止")
        self._emit_snapshot()

    def refresh_topic_status(self) -> None:
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker,
                "reset_rate_window",
                Qt.QueuedConnection,
            )
        self._topic_probe = "内部计数已刷新；可用「复制诊断命令」在终端核对 ros2 topic"
        self._emit_snapshot()

    def refresh_camera_topic_status(self) -> None:
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
            self._camera_topic_probe = "topic 探测线程未就绪"
            self._emit_snapshot()

    def diagnostic_commands(self) -> str:
        return diagnostic_shell_commands()

    def camera_diagnostic_commands(self) -> str:
        return camera_diagnostic_shell_commands()

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("shutting down global ROS2 bridge manager")
        self.set_rgb_bridge_enabled(False)
        self.set_depth_bridge_enabled(False)
        self.register_rgb_stream(None)
        self.stop_rviz()
        self._stop_probe_worker()
        self.stop_bridge()

    def snapshot(self) -> Ros2RvizPanelSnapshot:
        json_connected = False
        if self._session is not None:
            json_connected = self._session.is_connected()
        bridge_running = self._thread is not None or self._bridge_status.running
        origin_summary = ""
        if self._session is not None:
            origin_summary = self._session.odom_origin_summary()
        return Ros2RvizPanelSnapshot(
            env=ros2_status(),
            bridge_running=bridge_running,
            bridge_status=self._bridge_status,
            json_connected=json_connected,
            rviz_running=self._rviz.is_running(),
            rviz_error=self._rviz.last_error,
            topic_probe=self._topic_probe,
            origin_policy=ORIGIN_POLICY_LABEL,
            origin_summary=origin_summary,
        )

    def camera_snapshot(self) -> CameraRos2PanelSnapshot:
        bridge_running = self._thread is not None or self._bridge_status.running
        url = resolve_mjpeg_url_for_robot(self._robot) if self._robot else ""
        return CameraRos2PanelSnapshot(
            env=ros2_status(),
            bridge_running=bridge_running,
            bridge_status=self._bridge_status,
            topic_probe=self._camera_topic_probe,
            topic_probe_result=self._topic_probe_result,
            mjpeg_url=url,
            rviz_running=self._rviz.is_running(),
            rviz_error=self._rviz.last_error,
            diagnostics_expanded=self._diagnostics_expanded,
        )

    def _tee_rgb_jpeg(self, jpeg: bytes) -> None:
        if not self._rgb_tee_enabled or not jpeg or self._worker is None:
            return
        if self._rgb_mailbox.put(jpeg):
            QMetaObject.invokeMethod(
                self._worker,
                "deliver_rgb_mailbox",
                Qt.QueuedConnection,
            )

    def offer_depth_bridge_frame(
        self, header: dict, data: bytes, camera_info: Optional[dict]
    ) -> None:
        if not self._depth_tee_enabled or self._worker is None:
            return
        frame = DepthBridgeFrame(header=header, data=data, camera_info=camera_info)
        if self._depth_mailbox.put(frame):
            QMetaObject.invokeMethod(
                self._worker,
                "deliver_depth_mailbox",
                Qt.QueuedConnection,
            )

    def _replay_session_cache(self, session: "RobotSession") -> None:
        if self._worker is None:
            return
        if session.last_odom is not None:
            self._forward_odom_base(session.last_odom)
        cached = (
            (session.last_odom_raw, "on_odom_raw"),
            (session.last_odom_laser, "on_odom_laser"),
            (session.last_base_status, "on_base_status"),
            (session.last_laser_scan, "on_laser_scan"),
        )
        for payload, slot_name in cached:
            if payload is None:
                continue
            QMetaObject.invokeMethod(
                self._worker,
                slot_name,
                Qt.QueuedConnection,
                Q_ARG(object, payload),
            )

    def _connect_session(self, session: "RobotSession") -> None:
        if self._worker is None:
            return
        pairs = (
            (session.odom_updated, self._forward_odom_base),
            (session.odom_raw_updated, self._worker.on_odom_raw),
            (session.odom_laser_updated, self._worker.on_odom_laser),
            (session.base_status_updated, self._worker.on_base_status),
            (session.laser_scan_updated, self._worker.on_laser_scan),
        )
        for signal, slot in pairs:
            signal.connect(slot, Qt.QueuedConnection)
            self._session_slots.append((signal, slot))

    def _normalized_odom_base(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        if self._session is None:
            return msg
        lx, ly, yaw = self._session.relative_odom_pose(msg)
        out = dict(msg)
        out["x"] = lx
        out["y"] = ly
        out["yaw"] = yaw
        return out

    def _forward_odom_base(self, msg: object) -> None:
        if self._worker is None or not isinstance(msg, dict):
            return
        was_set = (
            self._session.odom_origin_is_set() if self._session is not None else True
        )
        normalized = self._normalized_odom_base(msg)
        QMetaObject.invokeMethod(
            self._worker,
            "on_odom_base",
            Qt.QueuedConnection,
            Q_ARG(object, normalized),
        )
        if (
            self._session is not None
            and not was_set
            and self._session.odom_origin_is_set()
        ):
            self._emit_snapshot()

    def _disconnect_session(self) -> None:
        for signal, slot in self._session_slots:
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        self._session_slots.clear()

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
        self._camera_topic_probe = format_probe_summary(
            result, topics=CAMERA_DIAGNOSTIC_TOPICS
        )
        self._emit_snapshot()

    def _on_bridge_status(self, status: object) -> None:
        if isinstance(status, BridgeRuntimeStatus):
            self._bridge_status = status
        self._emit_snapshot()

    def _on_bridge_failed(self, detail: str) -> None:
        logger.error("ROS2 bridge failed: %s", detail)
        self._bridge_status = BridgeRuntimeStatus(
            running=False, last_error=detail
        )
        self._emit_action_message(detail)
        self._emit_snapshot()

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
