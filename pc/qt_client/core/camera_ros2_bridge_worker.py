"""MJPEG -> /camera/image_raw (rgb8, ~5fps). Future: CompressedImage for lighter ROS2 transport."""

from __future__ import annotations

import logging
import time
from array import array
from dataclasses import dataclass, field
from typing import Dict, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot, QMetaObject, Qt, Q_ARG

from core.mjpeg_reader import MjpegReaderThread
from core.robot_frames import (
    BASE_FRAME,
    CAMERA_FRAME,
    CAMERA_ROLL,
    CAMERA_PITCH,
    CAMERA_ROS_TOPIC,
    CAMERA_X,
    CAMERA_Y,
    CAMERA_YAW,
    CAMERA_Z,
    euler_to_quaternion,
)
from core.ros2_context_ref import acquire_rclpy, release_rclpy
from core.ros2_runtime import Ros2RuntimeError, require_ros2_bridge
from core.ros_image_codec import jpeg_to_rgb8

logger = logging.getLogger(__name__)

try:
    import rclpy
    from geometry_msgs.msg import Quaternion, TransformStamped
    from rclpy.node import Node
    from sensor_msgs.msg import Image
    from tf2_ros import StaticTransformBroadcaster

    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False


def _camera_rotation_quaternion() -> Quaternion:
    qx, qy, qz, qw = euler_to_quaternion(CAMERA_ROLL, CAMERA_PITCH, CAMERA_YAW)
    q = Quaternion()
    q.x = qx
    q.y = qy
    q.z = qz
    q.w = qw
    return q


@dataclass
class CameraBridgeRuntimeStatus:
    running: bool = False
    publish_hz: Dict[str, float] = field(default_factory=dict)
    last_source_ms: Dict[str, int] = field(default_factory=dict)
    tf_static_ok: bool = False
    mjpeg_status: str = ""
    last_error: str = ""


class _CameraBridgeNode:
    def __init__(self) -> None:
        if not _ROS2_AVAILABLE:
            raise RuntimeError("ROS2 dependencies not available")
        acquire_rclpy()
        self._node = Node("xtark_camera_ros2_bridge")
        self._base_frame = BASE_FRAME
        self._camera_frame = CAMERA_FRAME
        self._image_pub = self._node.create_publisher(Image, CAMERA_ROS_TOPIC, 2)
        self._static_tf = StaticTransformBroadcaster(self._node)
        self._counts: Dict[str, int] = {}
        self._window_start = time.monotonic()
        self._last_source_ms: Dict[str, int] = {}
        self._tf_static_ok = False
        self._mjpeg_status = ""
        self._last_error = ""
        self._publish_static_camera_tf()

    def destroy(self) -> None:
        if rclpy.ok():
            self._node.destroy_node()
        release_rclpy()

    def spin_once(self) -> None:
        rclpy.spin_once(self._node, timeout_sec=0)

    def runtime_status(self) -> CameraBridgeRuntimeStatus:
        elapsed = max(time.monotonic() - self._window_start, 0.001)
        hz = {topic: count / elapsed for topic, count in self._counts.items()}
        return CameraBridgeRuntimeStatus(
            running=True,
            publish_hz=hz,
            last_source_ms=dict(self._last_source_ms),
            tf_static_ok=self._tf_static_ok,
            mjpeg_status=self._mjpeg_status,
            last_error=self._last_error,
        )

    def reset_rate_window(self) -> None:
        self._counts = {}
        self._window_start = time.monotonic()

    def set_mjpeg_status(self, text: str) -> None:
        self._mjpeg_status = text

    def _bump(self, topic: str) -> None:
        self._counts[topic] = self._counts.get(topic, 0) + 1

    def _publish_static_camera_tf(self) -> None:
        msg = TransformStamped()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.header.frame_id = self._base_frame
        msg.child_frame_id = self._camera_frame
        msg.transform.translation.x = CAMERA_X
        msg.transform.translation.y = CAMERA_Y
        msg.transform.translation.z = CAMERA_Z
        msg.transform.rotation = _camera_rotation_quaternion()
        self._static_tf.sendTransform(msg)
        self._tf_static_ok = True
        self._bump("/tf_static")

    def publish_camera_jpeg(self, jpeg: bytes) -> None:
        width, height, rgb = jpeg_to_rgb8(jpeg)
        msg = Image()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.header.frame_id = self._camera_frame
        msg.height = height
        msg.width = width
        msg.encoding = "rgb8"
        msg.is_bigendian = 0
        msg.step = width * 3
        msg.data = array("B", rgb)
        self._image_pub.publish(msg)
        self._bump(CAMERA_ROS_TOPIC)
        self._last_source_ms["camera_image"] = int(time.time() * 1000)


class CameraRos2BridgeWorker(QObject):
    status_updated = pyqtSignal(object)
    bridge_failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bridge: Optional[_CameraBridgeNode] = None
        self._mjpeg_url = ""
        self._camera_reader: Optional[MjpegReaderThread] = None
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(20)
        self._spin_timer.timeout.connect(self._spin_once)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._emit_status)

    @pyqtSlot(str)
    def set_mjpeg_url(self, url: str) -> None:
        self._mjpeg_url = (url or "").strip()

    def _start_camera_feed(self) -> None:
        self._stop_camera_feed()
        if not self._mjpeg_url:
            if self._bridge is not None:
                self._bridge.set_mjpeg_status("未配置 MJPEG URL")
            return
        if self._bridge is not None:
            self._bridge.set_mjpeg_status("Connecting...")

        def on_jpeg(jpeg: bytes) -> None:
            QMetaObject.invokeMethod(
                self,
                "on_camera_jpeg",
                Qt.QueuedConnection,
                Q_ARG(bytes, jpeg),
            )

        def on_status(text: str) -> None:
            if self._bridge is not None:
                self._bridge.set_mjpeg_status(text)

        self._camera_reader = MjpegReaderThread(
            self._mjpeg_url,
            on_jpeg,
            on_status=on_status,
            min_frame_interval_s=0.2,  # 约 5fps，减轻 Bridge CPU/带宽
        )
        self._camera_reader.start()

    def _stop_camera_feed(self) -> None:
        reader = self._camera_reader
        self._camera_reader = None
        if reader is None:
            return
        reader.stop()
        reader.join(timeout=3.0)

    @pyqtSlot()
    def start_bridge(self) -> None:
        if self._bridge is not None:
            return
        try:
            require_ros2_bridge()
        except Ros2RuntimeError as exc:
            self.bridge_failed.emit(str(exc))
            return
        if not _ROS2_AVAILABLE:
            self.bridge_failed.emit("ROS2 依赖未安装")
            return
        try:
            self._bridge = _CameraBridgeNode()
        except Exception as exc:
            logger.exception("camera ROS2 bridge start failed")
            self.bridge_failed.emit(str(exc))
            self._bridge = None
            return
        self._spin_timer.start()
        self._status_timer.start()
        self._start_camera_feed()
        logger.info("camera ROS2 bridge started")
        self._emit_status()

    @pyqtSlot()
    def stop_bridge(self) -> None:
        self._stop_camera_feed()
        self._spin_timer.stop()
        self._status_timer.stop()
        if self._bridge is not None:
            try:
                self._bridge.destroy()
            except Exception:
                logger.exception("camera bridge destroy failed")
            self._bridge = None
        logger.info("camera ROS2 bridge stopped")
        self.status_updated.emit(CameraBridgeRuntimeStatus(running=False))

    @pyqtSlot()
    def reset_rate_window(self) -> None:
        if self._bridge is not None:
            self._bridge.reset_rate_window()

    @pyqtSlot(bytes)
    def on_camera_jpeg(self, jpeg: bytes) -> None:
        if self._bridge is None or not jpeg:
            return
        try:
            self._bridge.publish_camera_jpeg(jpeg)
        except Exception as exc:
            self._bridge._last_error = str(exc)
            logger.exception("publish %s failed", CAMERA_ROS_TOPIC)

    def _spin_once(self) -> None:
        if self._bridge is None:
            return
        try:
            self._bridge.spin_once()
        except Exception as exc:
            logger.exception("camera rclpy spin failed")
            self.bridge_failed.emit(str(exc))

    def _emit_status(self) -> None:
        if self._bridge is None:
            self.status_updated.emit(CameraBridgeRuntimeStatus(running=False))
            return
        status = self._bridge.runtime_status()
        self._bridge.reset_rate_window()
        self.status_updated.emit(status)
