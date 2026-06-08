"""JSON feedback -> ROS2 topics + TF. Runs in the same process as app.py."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Optional

try:
    import rclpy
    from geometry_msgs.msg import Quaternion, TransformStamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from std_msgs.msg import String
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster

    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False


def _yaw_to_quaternion(yaw: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw * 0.5)
    q.w = math.cos(yaw * 0.5)
    return q


class Ros2Publisher:
    """Publish xtark JSON odom_base / base_status to ROS2."""

    def __init__(
        self,
        odom_frame: str = "odom",
        base_frame: str = "base_link",
        laser_frame: str = "laser",
        laser_z: float = 0.15,
    ) -> None:
        if not _ROS2_AVAILABLE:
            raise RuntimeError("rclpy not found; source /opt/ros/humble/setup.bash")
        if not rclpy.ok():
            rclpy.init()
        self._node = Node("qt_client_bridge")
        self._odom_frame = odom_frame
        self._base_frame = base_frame
        self._odom_pub = self._node.create_publisher(Odometry, "/odom_base", 10)
        self._status_pub = self._node.create_publisher(String, "/base_status", 2)
        self._tf_broadcaster = TransformBroadcaster(self._node)
        self._static_tf_broadcaster = StaticTransformBroadcaster(self._node)
        self._publish_static_laser(base_frame, laser_frame, laser_z)

    def spin_once(self) -> None:
        rclpy.spin_once(self._node, timeout_sec=0)

    def on_json(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "odom_base":
            self._publish_odom(msg)
        elif msg_type == "base_status":
            self._publish_status(msg)

    def shutdown(self) -> None:
        if not _ROS2_AVAILABLE or not rclpy.ok():
            return
        self._node.destroy_node()
        rclpy.shutdown()

    def _publish_static_laser(
        self, base_frame: str, laser_frame: str, laser_z: float
    ) -> None:
        msg = TransformStamped()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.header.frame_id = base_frame
        msg.child_frame_id = laser_frame
        msg.transform.translation.z = laser_z
        msg.transform.rotation.w = 1.0
        self._static_tf_broadcaster.sendTransform(msg)

    def _publish_odom(self, msg: Dict[str, Any]) -> None:
        x = float(msg.get("x", 0.0))
        y = float(msg.get("y", 0.0))
        yaw = float(msg.get("yaw", 0.0))
        stamp = self._node.get_clock().now().to_msg()

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.orientation = _yaw_to_quaternion(yaw)
        odom.twist.twist.linear.x = float(msg.get("linear_x", 0.0))
        odom.twist.twist.linear.y = float(msg.get("linear_y", 0.0))
        odom.twist.twist.angular.z = float(msg.get("angular_z", 0.0))
        self._odom_pub.publish(odom)

        tf_msg = TransformStamped()
        tf_msg.header.stamp = stamp
        tf_msg.header.frame_id = self._odom_frame
        tf_msg.child_frame_id = self._base_frame
        tf_msg.transform.translation.x = x
        tf_msg.transform.translation.y = y
        tf_msg.transform.rotation = _yaw_to_quaternion(yaw)
        self._tf_broadcaster.sendTransform(tf_msg)

    def _publish_status(self, msg: Dict[str, Any]) -> None:
        out = String()
        out.data = json.dumps(msg, separators=(",", ":"))
        self._status_pub.publish(out)


def try_create() -> Optional[Ros2Publisher]:
    if not _ROS2_AVAILABLE:
        return None
    try:
        return Ros2Publisher()
    except RuntimeError:
        return None
    except Exception as exc:
        print("WARN: Ros2Publisher init failed:", exc)
        return None


def ros2_unavailable_reason() -> str:
    try:
        import rclpy  # noqa: F401
        from tf2_ros import TransformBroadcaster  # noqa: F401
    except ImportError as exc:
        return "ROS2 未加载: {exc}".format(exc=exc)
    if not _ROS2_AVAILABLE:
        return "ROS2 消息模块导入失败，请 source /opt/ros/humble/setup.bash 后重启客户端"
    return "Ros2Publisher 初始化失败"
