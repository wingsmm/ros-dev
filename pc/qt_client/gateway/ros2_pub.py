"""JSON feedback -> ROS2 topics + TF. Runs in the same process as app.py."""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Callable, Dict, Optional, Tuple

CmdVelFn = Callable[[float, float, float], None]

logger = logging.getLogger(__name__)

try:
    import rclpy
    from geometry_msgs.msg import Quaternion, TransformStamped, Twist
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
        odom_frame: str = "odom",       # [固定] Nav2/SLAM 使用的里程计坐标系。
        base_frame: str = "base_link",  # [固定] ROS2 侧底盘坐标系，等价承接原车 base_footprint。
        laser_frame: str = "laser",     # [固定] RK3568 /scan 的 frame_id 应与此一致。
        # 保持原车 xtark XAS 的雷达外参。
        # ROS1 原厂 xtark_bringup 使用：
        #   base_footprint -> laser: x=0.05 y=0 z=0.10 yaw=pi
        # 当前 ROS2 桥接里，base_link 相当于 slam_toolbox/Nav2 使用的底盘坐标系。
        # 雷达 USB 从 xtark 挪到 RK3568 不会改变物理安装位置；
        # 只有实测传感器和底盘相对位置发生变化时，才应该修改这些值。
        laser_x: float = 0.05,          # [固定] 原车雷达相对底盘 x 偏移，单位 m。
        laser_y: float = 0.0,           # [固定] 原车雷达相对底盘 y 偏移，单位 m。
        laser_z: float = 0.10,          # [固定] 原车雷达相对底盘 z 高度，单位 m。
        laser_yaw: float = math.pi,     # [固定] 原车雷达朝向，pi 表示相对底盘旋转 180 度。
    ) -> None:
        if not _ROS2_AVAILABLE:
            raise RuntimeError("rclpy not found; source /opt/ros/humble/setup.bash")
        if not rclpy.ok():
            rclpy.init()
        self._node = Node("qt_client_bridge")
        self._odom_frame = odom_frame
        self._base_frame = base_frame
        self._odom_pub = self._node.create_publisher(Odometry, "/odom_base", 10)
        self._odom_nav_pub = self._node.create_publisher(Odometry, "/odom", 10)
        self._status_pub = self._node.create_publisher(String, "/base_status", 2)
        self._tf_broadcaster = TransformBroadcaster(self._node)
        self._static_tf_broadcaster = StaticTransformBroadcaster(self._node)
        self._cmd_vel_sub = self._node.create_subscription(
            Twist, "/cmd_vel", self._on_cmd_vel, 10
        )
        self._nav_cmd_enabled = False
        self._cmd_vel_callback: Optional[CmdVelFn] = None
        self._last_nav_cmd: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._publish_static_laser(
            base_frame, laser_frame, laser_x, laser_y, laser_z, laser_yaw
        )

    def set_nav_cmd_enabled(self, enabled: bool) -> None:
        self._nav_cmd_enabled = enabled
        if not enabled:
            self._last_nav_cmd = (0.0, 0.0, 0.0)

    def set_cmd_vel_callback(self, callback: Optional[CmdVelFn]) -> None:
        self._cmd_vel_callback = callback

    def _on_cmd_vel(self, msg: Twist) -> None:
        if not self._nav_cmd_enabled or self._cmd_vel_callback is None:
            return
        lx = float(msg.linear.x)
        ly = float(msg.linear.y)
        az = float(msg.angular.z)
        self._last_nav_cmd = (lx, ly, az)
        self._cmd_vel_callback(lx, ly, az)

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
        self,
        base_frame: str,
        laser_frame: str,
        laser_x: float,
        laser_y: float,
        laser_z: float,
        laser_yaw: float,
    ) -> None:
        msg = TransformStamped()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.header.frame_id = base_frame
        msg.child_frame_id = laser_frame
        msg.transform.translation.x = laser_x
        msg.transform.translation.y = laser_y
        msg.transform.translation.z = laser_z
        msg.transform.rotation = _yaw_to_quaternion(laser_yaw)
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
        self._odom_nav_pub.publish(odom)

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
        logger.warning("Ros2Publisher init failed: %s", exc)
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
