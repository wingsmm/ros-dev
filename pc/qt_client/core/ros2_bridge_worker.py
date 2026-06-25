from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.laser_scan_frame import LaserScanFrame
from core.robot_frames import (
    BASE_FRAME,
    LASER_FRAME,
    LASER_X,
    LASER_Y,
    LASER_Z,
    LASER_ROLL,
    LASER_PITCH,
    LASER_YAW,
    ODOM_FRAME,
    euler_to_quaternion,
)
from core.ros2_context_ref import acquire_rclpy, release_rclpy
from core.ros2_runtime import Ros2RuntimeError, require_ros2_bridge

logger = logging.getLogger(__name__)

try:
    import rclpy
    from builtin_interfaces.msg import Time as RosTime
    from geometry_msgs.msg import Quaternion, TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import Float32, String
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster

    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False


def _yaw_to_quaternion(yaw: float) -> Quaternion:
    qx, qy, qz, qw = euler_to_quaternion(0.0, 0.0, yaw)
    q = Quaternion()
    q.x = qx
    q.y = qy
    q.z = qz
    q.w = qw
    return q


def _laser_rotation_quaternion() -> Quaternion:
    qx, qy, qz, qw = euler_to_quaternion(LASER_ROLL, LASER_PITCH, LASER_YAW)
    q = Quaternion()
    q.x = qx
    q.y = qy
    q.z = qz
    q.w = qw
    return q


@dataclass
class BridgeRuntimeStatus:
    running: bool = False
    publish_hz: Dict[str, float] = field(default_factory=dict)
    last_source_ms: Dict[str, int] = field(default_factory=dict)
    tf_dynamic_ok: bool = False
    tf_static_ok: bool = False
    last_error: str = ""


class _BridgeNode:
    """ROS2 publishers; only touch from the bridge worker thread."""

    def __init__(self) -> None:
        if not _ROS2_AVAILABLE:
            raise RuntimeError("ROS2 dependencies not available")
        acquire_rclpy()
        self._node = Node("xtark_ros2_bridge")
        self._odom_frame = ODOM_FRAME
        self._base_frame = BASE_FRAME
        self._laser_frame = LASER_FRAME
        self._scan_pub = self._node.create_publisher(LaserScan, "/scan", 10)
        self._odom_pub = self._node.create_publisher(Odometry, "/odom", 10)
        self._odom_raw_pub = self._node.create_publisher(Odometry, "/odom_raw", 10)
        self._odom_laser_pub = self._node.create_publisher(
            Odometry, "/odom_laser", 10
        )
        self._status_pub = self._node.create_publisher(String, "/robot_status", 2)
        self._battery_pub = self._node.create_publisher(Float32, "/battery", 2)
        self._tf_broadcaster = TransformBroadcaster(self._node)
        self._static_tf_broadcaster = StaticTransformBroadcaster(self._node)
        self._counts: Dict[str, int] = {}
        self._window_start = time.monotonic()
        self._last_hz: Dict[str, float] = {}
        self._last_source_ms: Dict[str, int] = {}
        self._tf_dynamic_ok = False
        self._tf_static_ok = False
        self._last_error = ""
        self._publish_static_laser_tf()

    def destroy(self) -> None:
        if rclpy.ok():
            self._node.destroy_node()
        release_rclpy()

    def spin_once(self) -> None:
        rclpy.spin_once(self._node, timeout_sec=0)

    def runtime_status(self) -> BridgeRuntimeStatus:
        elapsed = max(time.monotonic() - self._window_start, 0.001)
        hz = {
            topic: count / elapsed
            for topic, count in self._counts.items()
        }
        return BridgeRuntimeStatus(
            running=True,
            publish_hz=hz,
            last_source_ms=dict(self._last_source_ms),
            tf_dynamic_ok=self._tf_dynamic_ok,
            tf_static_ok=self._tf_static_ok,
            last_error=self._last_error,
        )

    def reset_rate_window(self) -> None:
        self._counts = {}
        self._window_start = time.monotonic()

    def _bump(self, topic: str) -> None:
        self._counts[topic] = self._counts.get(topic, 0) + 1

    def _stamp_from_ms(self, stamp_ms: Any) -> RosTime:
        try:
            ms = int(stamp_ms)
        except (TypeError, ValueError):
            ms = int(time.time() * 1000)
        sec = ms // 1000
        nanosec = (ms % 1000) * 1_000_000
        stamp = RosTime()
        stamp.sec = sec
        stamp.nanosec = nanosec
        return stamp

    def _publish_static_laser_tf(self) -> None:
        stamp = self._node.get_clock().now().to_msg()
        laser_tf = TransformStamped()
        laser_tf.header.stamp = stamp
        laser_tf.header.frame_id = self._base_frame
        laser_tf.child_frame_id = self._laser_frame
        laser_tf.transform.translation.x = LASER_X
        laser_tf.transform.translation.y = LASER_Y
        laser_tf.transform.translation.z = LASER_Z
        laser_tf.transform.rotation = _laser_rotation_quaternion()
        self._static_tf_broadcaster.sendTransform(laser_tf)
        self._tf_static_ok = True
        self._bump("/tf_static")

    @staticmethod
    def _odom_from_json(
        msg: Dict[str, Any],
        *,
        parent_frame: str,
        child_frame: str,
        stamp: RosTime,
    ) -> Odometry:
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = parent_frame
        odom.child_frame_id = child_frame
        odom.pose.pose.position.x = float(msg.get("x", 0.0))
        odom.pose.pose.position.y = float(msg.get("y", 0.0))
        odom.pose.pose.orientation = _yaw_to_quaternion(float(msg.get("yaw", 0.0)))
        odom.twist.twist.linear.x = float(msg.get("linear_x", 0.0))
        odom.twist.twist.linear.y = float(msg.get("linear_y", 0.0))
        odom.twist.twist.angular.z = float(msg.get("angular_z", 0.0))
        return odom

    def publish_odom_base(self, msg: Dict[str, Any]) -> None:
        stamp_ms = msg.get("stamp_ms")
        stamp = self._stamp_from_ms(stamp_ms)
        odom = self._odom_from_json(
            msg,
            parent_frame=self._odom_frame,
            child_frame=self._base_frame,
            stamp=stamp,
        )
        self._odom_pub.publish(odom)
        self._bump("/odom")
        self._last_source_ms["odom_base"] = int(stamp_ms or 0)

        tf_msg = TransformStamped()
        tf_msg.header.stamp = stamp
        tf_msg.header.frame_id = self._odom_frame
        tf_msg.child_frame_id = self._base_frame
        tf_msg.transform.translation.x = odom.pose.pose.position.x
        tf_msg.transform.translation.y = odom.pose.pose.position.y
        tf_msg.transform.rotation = odom.pose.pose.orientation
        self._tf_broadcaster.sendTransform(tf_msg)
        self._tf_dynamic_ok = True
        self._bump("/tf")

    def publish_odom_raw(self, msg: Dict[str, Any]) -> None:
        stamp_ms = msg.get("stamp_ms")
        stamp = self._stamp_from_ms(stamp_ms)
        odom = self._odom_from_json(
            msg,
            parent_frame=self._odom_frame,
            child_frame=self._base_frame,
            stamp=stamp,
        )
        self._odom_raw_pub.publish(odom)
        self._bump("/odom_raw")
        self._last_source_ms["odom_raw"] = int(stamp_ms or 0)

    def publish_odom_laser(self, msg: Dict[str, Any]) -> None:
        stamp_ms = msg.get("stamp_ms")
        stamp = self._stamp_from_ms(stamp_ms)
        odom = self._odom_from_json(
            msg,
            parent_frame=self._odom_frame,
            child_frame=self._base_frame,
            stamp=stamp,
        )
        self._odom_laser_pub.publish(odom)
        self._bump("/odom_laser")
        self._last_source_ms["odom_laser"] = int(stamp_ms or 0)

    def publish_base_status(self, msg: Dict[str, Any]) -> None:
        out = String()
        out.data = json.dumps(msg, separators=(",", ":"))
        self._status_pub.publish(out)
        self._bump("/robot_status")
        self._last_source_ms["base_status"] = int(msg.get("stamp_ms") or 0)

        battery_v = msg.get("battery_v")
        if battery_v is not None:
            try:
                value = float(battery_v)
            except (TypeError, ValueError):
                return
            batt = Float32()
            batt.data = value
            self._battery_pub.publish(batt)
            self._bump("/battery")

    def publish_laser_scan(self, frame: LaserScanFrame) -> None:
        msg = LaserScan()
        msg.header.stamp = self._stamp_from_ms(frame.stamp_ms)
        msg.header.frame_id = self._laser_frame
        msg.angle_min = frame.angle_min
        msg.angle_max = frame.angle_max
        msg.angle_increment = frame.angle_increment
        msg.range_min = frame.range_min
        msg.range_max = frame.range_max
        msg.ranges = [
            float("inf") if distance is None else float(distance)
            for distance in frame.ranges
        ]
        self._scan_pub.publish(msg)
        self._bump("/scan")
        self._last_source_ms["laser_scan"] = int(frame.stamp_ms)


class Ros2BridgeWorker(QObject):
    """Runs rclpy in a dedicated QThread; receives session telemetry via slots."""

    status_updated = pyqtSignal(object)
    bridge_failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bridge: Optional[_BridgeNode] = None
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(20)
        self._spin_timer.timeout.connect(self._spin_once)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._emit_status)

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
            self.bridge_failed.emit(
                "ROS2 依赖未安装，请通过 ./run.sh 启动并检查启动日志"
            )
            return
        try:
            self._bridge = _BridgeNode()
        except Exception as exc:
            logger.exception("ROS2 bridge start failed")
            self.bridge_failed.emit(str(exc))
            self._bridge = None
            return
        self._spin_timer.start()
        self._status_timer.start()
        logger.info("ROS2 bridge started (node=xtark_ros2_bridge)")
        self._emit_status()

    @pyqtSlot()
    def stop_bridge(self) -> None:
        self._spin_timer.stop()
        self._status_timer.stop()
        if self._bridge is not None:
            try:
                self._bridge.destroy()
            except Exception:
                logger.exception("ROS2 bridge destroy failed")
            self._bridge = None
        logger.info("ROS2 bridge stopped")
        self.status_updated.emit(BridgeRuntimeStatus(running=False))

    @pyqtSlot()
    def reset_rate_window(self) -> None:
        if self._bridge is not None:
            self._bridge.reset_rate_window()

    @pyqtSlot(object)
    def on_odom_base(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_odom_base(msg)
        except Exception as exc:
            self._bridge._last_error = str(exc)
            logger.exception("publish /odom failed")

    @pyqtSlot(object)
    def on_odom_raw(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_odom_raw(msg)
        except Exception as exc:
            self._bridge._last_error = str(exc)
            logger.exception("publish /odom_raw failed")

    @pyqtSlot(object)
    def on_odom_laser(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_odom_laser(msg)
        except Exception as exc:
            self._bridge._last_error = str(exc)
            logger.exception("publish /odom_laser failed")

    @pyqtSlot(object)
    def on_base_status(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_base_status(msg)
        except Exception as exc:
            self._bridge._last_error = str(exc)
            logger.exception("publish /robot_status failed")

    @pyqtSlot(object)
    def on_laser_scan(self, frame: object) -> None:
        if self._bridge is None or not isinstance(frame, LaserScanFrame):
            return
        try:
            self._bridge.publish_laser_scan(frame)
        except Exception as exc:
            self._bridge._last_error = str(exc)
            logger.exception("publish /scan failed")

    def _spin_once(self) -> None:
        if self._bridge is None:
            return
        try:
            self._bridge.spin_once()
        except Exception as exc:
            logger.exception("rclpy spin failed")
            self.bridge_failed.emit(str(exc))

    def _emit_status(self) -> None:
        if self._bridge is None:
            self.status_updated.emit(BridgeRuntimeStatus(running=False))
            return
        status = self._bridge.runtime_status()
        self._bridge.reset_rate_window()
        self.status_updated.emit(status)
