from __future__ import annotations

import json
import logging
import os
import time
from array import array
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.laser_scan_frame import LaserScanFrame
from core.latest_frame_mailbox import DepthBridgeFrame
from core.robot_frames import (
    BASE_FRAME,
    CAMERA_FRAME,
    CAMERA_OPTICAL_FRAME,
    CAMERA_ROLL,
    CAMERA_PITCH,
    CAMERA_ROS_TOPIC,
    CAMERA_X,
    CAMERA_Y,
    CAMERA_YAW,
    CAMERA_Z,
    LASER_FRAME,
    LASER_X,
    LASER_Y,
    LASER_Z,
    LASER_ROLL,
    LASER_PITCH,
    LASER_YAW,
    ODOM_FRAME,
    camera_link_to_optical_quaternion,
    euler_to_quaternion,
)
from core.camera_depth_colormap import decode_depth_array
from core.camera_topics import (
    CAMERA_DEPTH_IMAGE_TOPIC,
    CAMERA_DEPTH_INFO_TOPIC,
    CAMERA_DEPTH_POINTS_TOPIC,
)
from core.ros2_runtime import Ros2RuntimeError, require_ros2_bridge
from core.ros_image_codec import jpeg_to_rgb8

logger = logging.getLogger(__name__)

_BRIDGE_RGB_MAX_FPS = float(os.environ.get("XTARK_BRIDGE_RGB_MAX_FPS", "5") or "5")
_BRIDGE_DEPTH_MAX_FPS = float(os.environ.get("XTARK_BRIDGE_DEPTH_MAX_FPS", "5") or "5")
_POINTCLOUD_LOG_INTERVAL_S = 5.0
_CAMERA_POINTCLOUD_ENABLE = os.environ.get(
    "CAMERA_POINTCLOUD_ENABLE", "1"
).strip().lower() in {"1", "true", "yes", "on"}
_CAMERA_POINTCLOUD_MAX_FPS = float(
    os.environ.get("CAMERA_POINTCLOUD_MAX_FPS", "2") or "2"
)
_CAMERA_POINTCLOUD_STRIDE = max(
    1, int(os.environ.get("CAMERA_POINTCLOUD_STRIDE", "4") or "4")
)
_CAMERA_POINTCLOUD_MIN_RANGE_M = float(
    os.environ.get("CAMERA_POINTCLOUD_MIN_RANGE_M", "0.25") or "0.25"
)
_CAMERA_POINTCLOUD_MAX_RANGE_M = float(
    os.environ.get("CAMERA_POINTCLOUD_MAX_RANGE_M", "5.0") or "5.0"
)
_CAMERA_POINTCLOUD_REQUIRE_SUBSCRIBER = os.environ.get(
    "CAMERA_POINTCLOUD_REQUIRE_SUBSCRIBER", "0"
).strip().lower() in {"1", "true", "yes", "on"}
_CAMERA_DEPTH_RAW_REQUIRE_SUBSCRIBER = os.environ.get(
    "CAMERA_DEPTH_RAW_REQUIRE_SUBSCRIBER", "1"
).strip().lower() in {"1", "true", "yes", "on"}
_DEPTH_FX_FALLBACK = float(os.environ.get("DEPTH_FX", "578.579") or "578.579")
_DEPTH_FY_FALLBACK = float(os.environ.get("DEPTH_FY", "579.358") or "579.358")
_DEPTH_CX_FALLBACK = float(os.environ.get("DEPTH_CX", "679.157") or "679.157")
_DEPTH_CY_FALLBACK = float(os.environ.get("DEPTH_CY", "323.147") or "323.147")


def _bridge_min_interval_s(max_fps: float) -> float:
    return 1.0 / max(max_fps, 0.1)


try:
    import rclpy
    from builtin_interfaces.msg import Time as RosTime
    from geometry_msgs.msg import Quaternion, TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from sensor_msgs.msg import CameraInfo, Image, LaserScan, PointCloud2, PointField
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


def _camera_rotation_quaternion() -> Quaternion:
    qx, qy, qz, qw = euler_to_quaternion(CAMERA_ROLL, CAMERA_PITCH, CAMERA_YAW)
    q = Quaternion()
    q.x = qx
    q.y = qy
    q.z = qz
    q.w = qw
    return q


def _camera_optical_rotation_quaternion() -> Quaternion:
    qx, qy, qz, qw = camera_link_to_optical_quaternion()
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
    camera_tf_static_ok: bool = False
    rgb_ingress_status: str = ""
    last_error: str = ""


class _BridgeNode:
    """ROS2 publishers; only touch from the bridge worker thread."""

    def __init__(self) -> None:
        if not _ROS2_AVAILABLE:
            raise RuntimeError("ROS2 dependencies not available")
        self._context = rclpy.context.Context()
        rclpy.init(context=self._context)
        try:
            self._node = Node("xtark_ros2_bridge", context=self._context)
        except Exception:
            if self._context.ok():
                rclpy.shutdown(context=self._context)
            raise
        self._executor = SingleThreadedExecutor(context=self._context)
        self._executor.add_node(self._node)
        self._odom_frame = ODOM_FRAME
        self._base_frame = BASE_FRAME
        self._laser_frame = LASER_FRAME
        self._camera_frame = CAMERA_FRAME
        self._camera_optical_frame = CAMERA_OPTICAL_FRAME
        self._scan_pub = self._node.create_publisher(LaserScan, "/scan", 10)
        self._odom_pub = self._node.create_publisher(Odometry, "/odom", 10)
        self._odom_raw_pub = self._node.create_publisher(Odometry, "/odom_raw", 10)
        self._odom_laser_pub = self._node.create_publisher(
            Odometry, "/odom_laser", 10
        )
        self._status_pub = self._node.create_publisher(String, "/robot_status", 2)
        self._battery_pub = self._node.create_publisher(Float32, "/battery", 2)
        self._image_pub = self._node.create_publisher(Image, CAMERA_ROS_TOPIC, 2)
        self._depth_image_pub = self._node.create_publisher(
            Image, CAMERA_DEPTH_IMAGE_TOPIC, 2
        )
        self._depth_info_pub = self._node.create_publisher(
            CameraInfo, CAMERA_DEPTH_INFO_TOPIC, 2
        )
        self._depth_points_pub = None
        if _CAMERA_POINTCLOUD_ENABLE:
            self._depth_points_pub = self._node.create_publisher(
                PointCloud2,
                CAMERA_DEPTH_POINTS_TOPIC,
                2,
            )
        self._last_depth_camera_info: Optional[Dict[str, Any]] = None
        self._last_pointcloud_publish_mono = 0.0
        self._last_pointcloud_log_mono = 0.0
        self._last_pointcloud_slow_log_mono = 0.0
        self._last_pointcloud_no_sub_log_mono = 0.0
        self._last_pointcloud_pause_log_mono = 0.0
        self._pointcloud_first_publish_logged = False
        self._pointcloud_stream_enabled = True
        self._pointcloud_min_interval_s = _bridge_min_interval_s(
            _CAMERA_POINTCLOUD_MAX_FPS
        )
        self._tf_broadcaster = TransformBroadcaster(self._node)
        self._static_tf_broadcaster = StaticTransformBroadcaster(self._node)
        self._counts: Dict[str, int] = {}
        self._window_start = time.monotonic()
        self._last_source_ms: Dict[str, int] = {}
        self._tf_dynamic_ok = False
        self._tf_static_ok = False
        self._camera_tf_static_ok = False
        self._rgb_ingress_status = ""
        self._last_error = ""
        self._publish_static_laser_tf()
        self._publish_static_camera_tf()
        logger.info(
            "camera pointcloud config: enabled=%s topic=%s max_fps=%.2f stride=%d "
            "range=%.2f..%.2fm require_subscriber=%s depth_raw_require_subscriber=%s "
            "fallback_K=(fx=%.1f,fy=%.1f,cx=%.1f,cy=%.1f)",
            _CAMERA_POINTCLOUD_ENABLE,
            CAMERA_DEPTH_POINTS_TOPIC,
            _CAMERA_POINTCLOUD_MAX_FPS,
            _CAMERA_POINTCLOUD_STRIDE,
            _CAMERA_POINTCLOUD_MIN_RANGE_M,
            _CAMERA_POINTCLOUD_MAX_RANGE_M,
            _CAMERA_POINTCLOUD_REQUIRE_SUBSCRIBER,
            _CAMERA_DEPTH_RAW_REQUIRE_SUBSCRIBER,
            _DEPTH_FX_FALLBACK,
            _DEPTH_FY_FALLBACK,
            _DEPTH_CX_FALLBACK,
            _DEPTH_CY_FALLBACK,
        )

    def destroy(self) -> None:
        try:
            try:
                self._executor.remove_node(self._node)
            except Exception:
                logger.debug("ROS2 bridge executor remove_node failed", exc_info=True)
            if self._context.ok():
                self._node.destroy_node()
        finally:
            if self._context.ok():
                rclpy.shutdown(context=self._context)

    def spin_once(self) -> None:
        if not self._context.ok():
            raise RuntimeError("ROS2 bridge context is not valid")
        self._executor.spin_once(timeout_sec=0)

    def runtime_status(self) -> BridgeRuntimeStatus:
        elapsed = max(time.monotonic() - self._window_start, 0.001)
        hz = {topic: count / elapsed for topic, count in self._counts.items()}
        return BridgeRuntimeStatus(
            running=True,
            publish_hz=hz,
            last_source_ms=dict(self._last_source_ms),
            tf_dynamic_ok=self._tf_dynamic_ok,
            tf_static_ok=self._tf_static_ok,
            camera_tf_static_ok=self._camera_tf_static_ok,
            rgb_ingress_status=self._rgb_ingress_status,
            last_error=self._last_error,
        )

    def reset_rate_window(self) -> None:
        self._counts = {}
        self._window_start = time.monotonic()

    def set_rgb_ingress_status(self, text: str) -> None:
        self._rgb_ingress_status = text

    def set_pointcloud_stream_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._pointcloud_stream_enabled == enabled:
            return
        self._pointcloud_stream_enabled = enabled
        logger.info(
            "CAMERA_FLOW pointcloud_stream enabled=%s topic=%s",
            enabled,
            CAMERA_DEPTH_POINTS_TOPIC,
        )

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

    def _stamp_from_header(self, header: Dict[str, Any]) -> RosTime:
        sec = int(header.get("stamp_sec", 0))
        nsec = int(header.get("stamp_nsec", 0))
        stamp = RosTime()
        stamp.sec = sec
        stamp.nanosec = nsec
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

    def _publish_static_camera_tf(self) -> None:
        stamp = self._node.get_clock().now().to_msg()
        camera_tf = TransformStamped()
        camera_tf.header.stamp = stamp
        camera_tf.header.frame_id = self._base_frame
        camera_tf.child_frame_id = self._camera_frame
        camera_tf.transform.translation.x = CAMERA_X
        camera_tf.transform.translation.y = CAMERA_Y
        camera_tf.transform.translation.z = CAMERA_Z
        camera_tf.transform.rotation = _camera_rotation_quaternion()
        optical_tf = TransformStamped()
        optical_tf.header.stamp = stamp
        optical_tf.header.frame_id = self._camera_frame
        optical_tf.child_frame_id = self._camera_optical_frame
        optical_tf.transform.translation.x = 0.0
        optical_tf.transform.translation.y = 0.0
        optical_tf.transform.translation.z = 0.0
        optical_tf.transform.rotation = _camera_optical_rotation_quaternion()
        self._static_tf_broadcaster.sendTransform([camera_tf, optical_tf])
        self._camera_tf_static_ok = True
        self._bump("/tf_static")
        logger.info(
            "camera TF published: %s->%s xyz=(%.3f,%.3f,%.3f) rpy=(%.3f,%.3f,%.3f); "
            "%s->%s optical=standard",
            self._base_frame,
            self._camera_frame,
            CAMERA_X,
            CAMERA_Y,
            CAMERA_Z,
            CAMERA_ROLL,
            CAMERA_PITCH,
            CAMERA_YAW,
            self._camera_frame,
            self._camera_optical_frame,
        )

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

    def publish_rgb_jpeg(self, jpeg: bytes) -> None:
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
        self._rgb_ingress_status = "tee OK"

    def publish_depth_raw_frame(self, frame: DepthBridgeFrame) -> None:
        header = frame.header
        stamp_ms = int(header.get("stamp_sec", 0)) * 1000 + int(
            header.get("stamp_nsec", 0)
        ) // 1_000_000
        depth_image_subscribers = self._depth_image_pub.get_subscription_count()
        if (
            not _CAMERA_DEPTH_RAW_REQUIRE_SUBSCRIBER
            or depth_image_subscribers > 0
        ):
            msg = Image()
            msg.header.stamp = self._stamp_from_header(header)
            msg.header.frame_id = str(header.get("frame_id") or self._camera_frame)
            msg.height = int(header["height"])
            msg.width = int(header["width"])
            msg.encoding = str(header["encoding"])
            msg.is_bigendian = int(header.get("is_bigendian", 0))
            msg.step = int(header["step"])
            msg.data = array("B", frame.data)
            self._depth_image_pub.publish(msg)
            self._bump(CAMERA_DEPTH_IMAGE_TOPIC)
            self._last_source_ms["depth_image"] = stamp_ms
        if frame.camera_info is not None:
            self.publish_depth_camera_info(frame.camera_info)
        self._maybe_publish_depth_pointcloud(frame)

    def publish_depth_camera_info(self, info: Dict[str, Any]) -> None:
        self._last_depth_camera_info = dict(info)
        if (
            _CAMERA_DEPTH_RAW_REQUIRE_SUBSCRIBER
            and self._depth_info_pub.get_subscription_count() <= 0
        ):
            return
        msg = CameraInfo()
        msg.header.stamp = self._stamp_from_header(info)
        msg.header.frame_id = str(info.get("frame_id") or self._camera_frame)
        msg.height = int(info.get("height", 0))
        msg.width = int(info.get("width", 0))
        msg.distortion_model = str(info.get("distortion_model", ""))
        msg.d = [float(value) for value in info.get("d", [])]
        msg.k = [float(value) for value in info.get("k", [])]
        msg.r = [float(value) for value in info.get("r", [])]
        msg.p = [float(value) for value in info.get("p", [])]
        self._depth_info_pub.publish(msg)
        self._bump(CAMERA_DEPTH_INFO_TOPIC)
        stamp_ms = int(info.get("stamp_sec", 0)) * 1000 + int(
            info.get("stamp_nsec", 0)
        ) // 1_000_000
        self._last_source_ms["depth_camera_info"] = stamp_ms

    def _intrinsics_from_camera_info(
        self, info: Optional[Dict[str, Any]]
    ) -> tuple[float, float, float, float]:
        if info:
            k = info.get("k") or []
            if len(k) >= 6:
                return float(k[0]), float(k[4]), float(k[2]), float(k[5])
        return (
            _DEPTH_FX_FALLBACK,
            _DEPTH_FY_FALLBACK,
            _DEPTH_CX_FALLBACK,
            _DEPTH_CY_FALLBACK,
        )

    def _maybe_publish_depth_pointcloud(self, frame: DepthBridgeFrame) -> None:
        if self._depth_points_pub is None:
            return
        now = time.monotonic()
        if not self._pointcloud_stream_enabled:
            self._last_pointcloud_publish_mono = now
            if now - self._last_pointcloud_pause_log_mono >= _POINTCLOUD_LOG_INTERVAL_S:
                logger.info(
                    "CAMERA_FLOW pointcloud skipped paused topic=%s",
                    CAMERA_DEPTH_POINTS_TOPIC,
                )
                self._last_pointcloud_pause_log_mono = now
            return
        if now - self._last_pointcloud_publish_mono < self._pointcloud_min_interval_s:
            return
        if (
            _CAMERA_POINTCLOUD_REQUIRE_SUBSCRIBER
            and self._depth_points_pub.get_subscription_count() <= 0
        ):
            self._last_pointcloud_publish_mono = now
            if (
                now - self._last_pointcloud_no_sub_log_mono
                >= _POINTCLOUD_LOG_INTERVAL_S
            ):
                logger.info(
                    "CAMERA_FLOW pointcloud skipped no_subscriber topic=%s",
                    CAMERA_DEPTH_POINTS_TOPIC,
                )
                self._last_pointcloud_no_sub_log_mono = now
            return
        t0 = time.monotonic()
        header = frame.header
        width = int(header.get("width", 0))
        height = int(header.get("height", 0))
        if width <= 0 or height <= 0 or not frame.data:
            return
        info = frame.camera_info or self._last_depth_camera_info
        intrinsics_source = "camera_info" if info else "env_fallback"
        fx, fy, cx, cy = self._intrinsics_from_camera_info(info)
        try:
            import numpy as np

            depth_m = decode_depth_array(
                frame.data,
                width=width,
                height=height,
                encoding=str(header.get("encoding", "")),
            )
            stride = _CAMERA_POINTCLOUD_STRIDE
            depth_sampled = depth_m[::stride, ::stride]
            us = np.arange(0, width, stride, dtype=np.float32)
            vs = np.arange(0, height, stride, dtype=np.float32)
            uu, vv = np.meshgrid(us, vs)
            z = depth_sampled
            valid = (
                np.isfinite(z)
                & (z >= _CAMERA_POINTCLOUD_MIN_RANGE_M)
                & (z <= _CAMERA_POINTCLOUD_MAX_RANGE_M)
            )
            if not np.any(valid):
                self._last_pointcloud_publish_mono = now
                if now - self._last_pointcloud_log_mono >= _POINTCLOUD_LOG_INTERVAL_S:
                    logger.warning(
                        "camera pointcloud skipped: no valid depth frame=%dx%d "
                        "encoding=%s stride=%d range=%.2f..%.2fm K_source=%s",
                        width,
                        height,
                        str(header.get("encoding", "")),
                        _CAMERA_POINTCLOUD_STRIDE,
                        _CAMERA_POINTCLOUD_MIN_RANGE_M,
                        _CAMERA_POINTCLOUD_MAX_RANGE_M,
                        intrinsics_source,
                    )
                    self._last_pointcloud_log_mono = now
                return
            x = (uu - cx) * z / fx
            y = (vv - cy) * z / fy
            pts = np.stack([x[valid], y[valid], z[valid]], axis=-1).astype(
                np.float32
            )
            point_count = int(pts.shape[0])
            cloud = PointCloud2()
            cloud.header.stamp = self._stamp_from_header(header)
            cloud.header.frame_id = self._camera_optical_frame
            cloud.height = 1
            cloud.width = point_count
            cloud.is_bigendian = False
            cloud.is_dense = True
            cloud.point_step = 12
            cloud.row_step = point_count * 12
            cloud.fields = [
                PointField(
                    name="x",
                    offset=0,
                    datatype=PointField.FLOAT32,
                    count=1,
                ),
                PointField(
                    name="y",
                    offset=4,
                    datatype=PointField.FLOAT32,
                    count=1,
                ),
                PointField(
                    name="z",
                    offset=8,
                    datatype=PointField.FLOAT32,
                    count=1,
                ),
            ]
            cloud.data = pts.tobytes()
            subscriber_count = int(self._depth_points_pub.get_subscription_count())
            self._depth_points_pub.publish(cloud)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            self._bump(CAMERA_DEPTH_POINTS_TOPIC)
            stamp_ms = int(header.get("stamp_sec", 0)) * 1000 + int(
                header.get("stamp_nsec", 0)
            ) // 1_000_000
            self._last_source_ms["depth_points"] = stamp_ms
            self._last_pointcloud_publish_mono = now
            if (
                not self._pointcloud_first_publish_logged
                or now - self._last_pointcloud_log_mono >= _POINTCLOUD_LOG_INTERVAL_S
            ):
                z_valid = z[valid]
                logger.info(
                    "CAMERA_FLOW pointcloud published points=%d compute=%.1fms "
                    "subscriber=%d topic=%s frame=%s sampled=%d valid=%.1f%% "
                    "range=%.2f..%.2fm stride=%d src=%dx%d encoding=%s",
                    point_count,
                    elapsed_ms,
                    subscriber_count,
                    CAMERA_DEPTH_POINTS_TOPIC,
                    self._camera_optical_frame,
                    int(z.size),
                    (point_count / max(int(z.size), 1)) * 100.0,
                    float(np.nanmin(z_valid)),
                    float(np.nanmax(z_valid)),
                    _CAMERA_POINTCLOUD_STRIDE,
                    width,
                    height,
                    str(header.get("encoding", "")),
                )
                self._pointcloud_first_publish_logged = True
                self._last_pointcloud_log_mono = now
            if elapsed_ms >= 30.0 and now - self._last_pointcloud_slow_log_mono >= 5.0:
                logger.warning(
                    "CAMERA_FLOW pointcloud slow compute=%.1fms points=%d "
                    "subscriber=%d stride=%d src=%dx%d",
                    elapsed_ms,
                    point_count,
                    subscriber_count,
                    _CAMERA_POINTCLOUD_STRIDE,
                    width,
                    height,
                )
                self._last_pointcloud_slow_log_mono = now
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("publish %s failed", CAMERA_DEPTH_POINTS_TOPIC)


class Ros2BridgeWorker(QObject):
    """Runs rclpy in a dedicated QThread; receives telemetry and ingress tee via slots."""

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
        self._rgb_mailbox: Optional[object] = None
        self._depth_mailbox: Optional[object] = None
        self._last_rgb_publish_mono = 0.0
        self._last_depth_publish_mono = 0.0
        self._rgb_min_interval_s = _bridge_min_interval_s(_BRIDGE_RGB_MAX_FPS)
        self._depth_min_interval_s = _bridge_min_interval_s(_BRIDGE_DEPTH_MAX_FPS)
        self._rgb_retry_armed = False
        self._depth_retry_armed = False
        self._stopping = False
        self._pointcloud_stream_enabled = True

    def bind_mailboxes(self, rgb_mailbox: object, depth_mailbox: object) -> None:
        self._rgb_mailbox = rgb_mailbox
        self._depth_mailbox = depth_mailbox

    @pyqtSlot()
    def start_bridge(self) -> None:
        if self._bridge is not None:
            return
        self._stopping = False
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
            self._bridge.set_pointcloud_stream_enabled(
                self._pointcloud_stream_enabled
            )
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
        self._stopping = True
        self._spin_timer.stop()
        self._status_timer.stop()
        bridge = self._bridge
        self._bridge = None
        if bridge is not None:
            try:
                bridge.destroy()
            except Exception:
                logger.exception("ROS2 bridge destroy failed")
        self._clear_mailboxes()
        logger.info("ROS2 bridge stopped")
        self.status_updated.emit(BridgeRuntimeStatus(running=False))

    def _fail_bridge(self, detail: str) -> None:
        if self._stopping:
            return
        self._stopping = True
        logger.error("ROS2 bridge worker stopping after failure: %s", detail)
        self._spin_timer.stop()
        self._status_timer.stop()
        bridge = self._bridge
        self._bridge = None
        self._clear_mailboxes()
        if bridge is not None:
            try:
                bridge.destroy()
            except Exception:
                logger.debug("ROS2 bridge destroy after failure failed", exc_info=True)
        self.status_updated.emit(BridgeRuntimeStatus(running=False, last_error=detail))
        self.bridge_failed.emit(detail)

    @pyqtSlot()
    def reset_rate_window(self) -> None:
        if self._bridge is not None:
            self._bridge.reset_rate_window()

    @pyqtSlot(bool)
    def set_pointcloud_stream_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._pointcloud_stream_enabled == enabled:
            return
        self._pointcloud_stream_enabled = enabled
        if self._bridge is not None:
            self._bridge.set_pointcloud_stream_enabled(enabled)
        else:
            logger.info("CAMERA_FLOW pointcloud_stream queued enabled=%s", enabled)

    @pyqtSlot()
    def deliver_rgb_mailbox(self) -> None:
        self._rgb_retry_armed = False
        mailbox = self._rgb_mailbox
        if self._bridge is None or mailbox is None:
            if mailbox is not None:
                mailbox.clear()
            return
        while True:
            now = time.monotonic()
            remaining_s = self._rgb_min_interval_s - (
                now - self._last_rgb_publish_mono
            )
            if remaining_s > 0:
                self._schedule_rgb_retry(remaining_s)
                return
            jpeg = mailbox.take()
            if jpeg is None:
                mailbox.finish_delivery_cycle()
                return
            try:
                self._bridge.publish_rgb_jpeg(jpeg)
            except Exception as exc:
                logger.exception("publish %s failed", CAMERA_ROS_TOPIC)
                self._fail_bridge(str(exc))
                return
            self._last_rgb_publish_mono = time.monotonic()
            if not mailbox.has_pending():
                mailbox.finish_delivery_cycle()
                return

    @pyqtSlot()
    def deliver_depth_mailbox(self) -> None:
        self._depth_retry_armed = False
        mailbox = self._depth_mailbox
        if self._bridge is None or mailbox is None:
            if mailbox is not None:
                mailbox.clear()
            return
        while True:
            now = time.monotonic()
            remaining_s = self._depth_min_interval_s - (
                now - self._last_depth_publish_mono
            )
            if remaining_s > 0:
                self._schedule_depth_retry(remaining_s)
                return
            frame = mailbox.take()
            if frame is None:
                mailbox.finish_delivery_cycle()
                return
            try:
                self._bridge.publish_depth_raw_frame(frame)
            except Exception as exc:
                logger.exception("publish depth frame failed")
                self._fail_bridge(str(exc))
                return
            self._last_depth_publish_mono = time.monotonic()
            if not mailbox.has_pending():
                mailbox.finish_delivery_cycle()
                return

    def _schedule_rgb_retry(self, delay_s: float) -> None:
        if self._rgb_retry_armed:
            return
        self._rgb_retry_armed = True
        QTimer.singleShot(max(1, int(delay_s * 1000)), self.deliver_rgb_mailbox)

    def _schedule_depth_retry(self, delay_s: float) -> None:
        if self._depth_retry_armed:
            return
        self._depth_retry_armed = True
        QTimer.singleShot(max(1, int(delay_s * 1000)), self.deliver_depth_mailbox)

    def _clear_mailboxes(self) -> None:
        self._rgb_retry_armed = False
        self._depth_retry_armed = False
        if self._rgb_mailbox is not None:
            self._rgb_mailbox.clear()
        if self._depth_mailbox is not None:
            self._depth_mailbox.clear()

    @pyqtSlot(object)
    def on_odom_base(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_odom_base(msg)
        except Exception as exc:
            logger.exception("publish /odom failed")
            self._fail_bridge(str(exc))

    @pyqtSlot(object)
    def on_odom_raw(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_odom_raw(msg)
        except Exception as exc:
            logger.exception("publish /odom_raw failed")
            self._fail_bridge(str(exc))

    @pyqtSlot(object)
    def on_odom_laser(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_odom_laser(msg)
        except Exception as exc:
            logger.exception("publish /odom_laser failed")
            self._fail_bridge(str(exc))

    @pyqtSlot(object)
    def on_base_status(self, msg: object) -> None:
        if self._bridge is None or not isinstance(msg, dict):
            return
        try:
            self._bridge.publish_base_status(msg)
        except Exception as exc:
            logger.exception("publish /robot_status failed")
            self._fail_bridge(str(exc))

    @pyqtSlot(object)
    def on_laser_scan(self, frame: object) -> None:
        if self._bridge is None or not isinstance(frame, LaserScanFrame):
            return
        try:
            self._bridge.publish_laser_scan(frame)
        except Exception as exc:
            logger.exception("publish /scan failed")
            self._fail_bridge(str(exc))

    def _spin_once(self) -> None:
        if self._bridge is None:
            return
        try:
            self._bridge.spin_once()
        except Exception as exc:
            logger.exception("rclpy spin failed")
            self._fail_bridge(str(exc))

    def _emit_status(self) -> None:
        if self._bridge is None:
            self.status_updated.emit(BridgeRuntimeStatus(running=False))
            return
        status = self._bridge.runtime_status()
        self._bridge.reset_rate_window()
        self.status_updated.emit(status)
