from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, QMetaObject, Q_ARG

from core.ros2_bridge_worker import BridgeRuntimeStatus, Ros2BridgeWorker
from core.app_shutdown import register_shutdown
from core.odom_session_origin import ORIGIN_POLICY_LABEL
from core.ros2_runtime import (
    Ros2RuntimeError,
    Ros2RuntimeStatus,
    require_ros2_bridge,
    require_ros2_rviz,
    ros2_status,
    rviz_robot_config_path,
)
from core.rviz_process_manager import RvizProcessManager

if TYPE_CHECKING:
    from core.robot_session import RobotSession

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


class Ros2BridgeManager(QObject):
    """Lifecycle for ROS2 bridge sidecar + RViz2; feeds RobotSession telemetry."""

    snapshot_updated = pyqtSignal(object)
    action_message = pyqtSignal(str)

    def __init__(
        self,
        session: Optional["RobotSession"] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._thread: Optional[QThread] = None
        self._worker: Optional[Ros2BridgeWorker] = None
        self._rviz = RvizProcessManager()
        self._bridge_status = BridgeRuntimeStatus()
        self._topic_probe = ""
        self._session_slots: list[tuple[object, object]] = []
        self._shutdown_done = False
        register_shutdown(self.shutdown, name="ros2_bridge_manager", priority=20)

    def set_session(self, session: Optional["RobotSession"]) -> None:
        if self._session is session:
            return
        self._disconnect_session()
        self._session = session
        if self._worker is not None and session is not None:
            self._connect_session(session)

    def start_bridge(self) -> bool:
        try:
            require_ros2_bridge()
        except Ros2RuntimeError as exc:
            self.action_message.emit(str(exc))
            self._emit_snapshot()
            return False
        if self._thread is not None:
            if self._bridge_status.running:
                self.action_message.emit("ROS2 Bridge 已在运行")
                return True
            self.stop_bridge()
        self._disconnect_session()
        self._thread = QThread(self)
        self._worker = Ros2BridgeWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start_bridge)
        self._worker.status_updated.connect(self._on_bridge_status)
        self._worker.bridge_failed.connect(self._on_bridge_failed)
        self._thread.start()
        if self._session is not None:
            self._connect_session(self._session)
            self._replay_session_cache(self._session)
        self.action_message.emit("正在启动 ROS2 Bridge…")
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
        self.action_message.emit("ROS2 Bridge 已停止")
        self._emit_snapshot()

    def start_rviz(self) -> bool:
        try:
            require_ros2_rviz()
        except Ros2RuntimeError as exc:
            self.action_message.emit(str(exc))
            self._emit_snapshot()
            return False
        if not self._rviz.start(rviz_robot_config_path()):
            self.action_message.emit(self._rviz.last_error or "RViz2 启动失败")
            self._emit_snapshot()
            return False
        self.action_message.emit("RViz2 已启动")
        self._emit_snapshot()
        return True

    def stop_rviz(self) -> None:
        self._rviz.stop()
        self.action_message.emit("RViz2 已停止")
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

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("shutting down ROS2 bridge manager (rviz + bridge)")
        self.stop_rviz()
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

    def _on_bridge_status(self, status: object) -> None:
        if isinstance(status, BridgeRuntimeStatus):
            self._bridge_status = status
        self._emit_snapshot()

    def _on_bridge_failed(self, detail: str) -> None:
        logger.error("ROS2 bridge failed: %s", detail)
        self._bridge_status = BridgeRuntimeStatus(
            running=False, last_error=detail
        )
        self.action_message.emit(detail)
        self._emit_snapshot()

    def _emit_snapshot(self) -> None:
        self.snapshot_updated.emit(self.snapshot())
