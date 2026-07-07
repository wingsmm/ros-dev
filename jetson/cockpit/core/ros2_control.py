"""ROS2 worker for the Jetson Qt cockpit.

Only talks to ROS2:
- publish geometry_msgs/Twist on /cmd_vel
- subscribe std_msgs/String on /vehicle/control_action
"""

from __future__ import annotations

import queue
import traceback

from PyQt5.QtCore import QThread, pyqtSignal


class Ros2ControlWorker(QThread):
    status_changed = pyqtSignal(str, bool)
    line = pyqtSignal(str)
    action_received = pyqtSignal(str)

    def __init__(
        self,
        cmd_vel_topic: str = "/cmd_vel",
        control_action_topic: str = "/vehicle/control_action",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._cmd_vel_topic = cmd_vel_topic
        self._control_action_topic = control_action_topic
        self._velocities: queue.Queue[tuple[float, float, float]] = queue.Queue()
        self._running = True

    def publish_velocity(self, linear_x: float, linear_y: float, angular_z: float) -> None:
        self._velocities.put((float(linear_x), float(linear_y), float(angular_z)))

    def publish_stop(self, repeat: int = 3) -> None:
        for _ in range(max(1, int(repeat))):
            self.publish_velocity(0.0, 0.0, 0.0)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        try:
            import rclpy
            from geometry_msgs.msg import Twist
            from std_msgs.msg import String
        except Exception as exc:  # pragma: no cover - depends on ROS env
            self.status_changed.emit("rclpy 导入失败", False)
            self.line.emit("rclpy 导入失败: %s" % exc)
            return

        node = None
        try:
            rclpy.init(args=None)
            node = rclpy.create_node("jetson_cockpit_qt")
            publisher = node.create_publisher(Twist, self._cmd_vel_topic, 10)

            def on_control_action(msg: String) -> None:
                self.action_received.emit(msg.data)

            node.create_subscription(
                String, self._control_action_topic, on_control_action, 10
            )
            self.status_changed.emit("就绪", True)
            self.line.emit("ROS2 就绪：发布 %s" % self._cmd_vel_topic)
            self.line.emit("ROS2 就绪：订阅 %s" % self._control_action_topic)

            while self._running:
                self._drain_velocities(publisher, Twist)
                rclpy.spin_once(node, timeout_sec=0.05)
        except Exception:
            self.status_changed.emit("错误", False)
            self.line.emit(traceback.format_exc())
        finally:
            if node is not None:
                node.destroy_node()
            if "rclpy" in locals() and rclpy.ok():
                rclpy.shutdown()
            self.status_changed.emit("已停止", False)

    def _drain_velocities(self, publisher, twist_type) -> None:
        while self._running:
            try:
                linear_x, linear_y, angular_z = self._velocities.get_nowait()
            except queue.Empty:
                return
            msg = twist_type()
            msg.linear.x = linear_x
            msg.linear.y = linear_y
            msg.angular.z = angular_z
            publisher.publish(msg)
            self.line.emit(
                "发布 %s lx=%.2f ly=%.2f az=%.2f"
                % (self._cmd_vel_topic, linear_x, linear_y, angular_z)
            )
