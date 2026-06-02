from __future__ import annotations

import json
import time
from typing import Optional

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import String


class BackendWatchdog(Node):
    """Publish lightweight health information for the active SLAM backend."""

    def __init__(self) -> None:
        super().__init__("slam_backend_watchdog")
        self.declare_parameter("mode", "mapping")
        self.declare_parameter("odom_topic", "/aft_mapped_to_init")
        self.declare_parameter("cloud_topic", "/cloud_registered")
        self.declare_parameter("timeout_sec", 2.0)
        self.declare_parameter("status_topic", "/slam_backend/status")

        self.mode = self.get_parameter("mode").get_parameter_value().string_value
        odom_topic = self.get_parameter("odom_topic").get_parameter_value().string_value
        cloud_topic = self.get_parameter("cloud_topic").get_parameter_value().string_value
        self.timeout_sec = self.get_parameter("timeout_sec").get_parameter_value().double_value
        status_topic = self.get_parameter("status_topic").get_parameter_value().string_value

        self.last_odom_time: Optional[float] = None
        self.last_cloud_time: Optional[float] = None
        self.odom_count = 0
        self.cloud_count = 0

        self.create_subscription(Odometry, odom_topic, self._on_odom, 10)
        self.create_subscription(PointCloud2, cloud_topic, self._on_cloud, 10)
        self.status_pub = self.create_publisher(String, status_topic, 10)
        self.create_timer(1.0, self._publish_status)

        self.get_logger().info(
            f"watching backend topics odom={odom_topic}, cloud={cloud_topic}, mode={self.mode}"
        )

    def _on_odom(self, _msg: Odometry) -> None:
        self.last_odom_time = time.monotonic()
        self.odom_count += 1

    def _on_cloud(self, _msg: PointCloud2) -> None:
        self.last_cloud_time = time.monotonic()
        self.cloud_count += 1

    def _publish_status(self) -> None:
        now = time.monotonic()
        odom_age = None if self.last_odom_time is None else now - self.last_odom_time
        cloud_age = None if self.last_cloud_time is None else now - self.last_cloud_time
        odom_ok = odom_age is not None and odom_age <= self.timeout_sec
        cloud_ok = cloud_age is not None and cloud_age <= self.timeout_sec

        status = {
            "mode": self.mode,
            "ok": bool(odom_ok and cloud_ok),
            "odom_ok": bool(odom_ok),
            "cloud_ok": bool(cloud_ok),
            "odom_count": self.odom_count,
            "cloud_count": self.cloud_count,
            "odom_age_sec": odom_age,
            "cloud_age_sec": cloud_age,
        }
        self.status_pub.publish(String(data=json.dumps(status, sort_keys=True)))


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = BackendWatchdog()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
