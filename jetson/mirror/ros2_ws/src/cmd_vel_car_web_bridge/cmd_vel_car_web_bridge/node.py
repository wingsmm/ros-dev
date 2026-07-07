"""Dry-run cmd_vel -> discrete action bridge.

First stage of the cockpit -> Jetson control link. Subscribes /cmd_vel
(geometry_msgs/Twist), maps it to one of five discrete actions
(FORWARD / BACKWARD / TURN_LEFT / TURN_RIGHT / STOP), logs it and
republishes on /vehicle/control_action (std_msgs/String).

This node intentionally does NOT talk to car_web or drive real motors.
Its only job is to verify that the ROS2 DDS path
    cockpit (PC/WSL)  ->  /cmd_vel  ->  Jetson ros2_ws
works end to end.
"""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String

ACTION_FORWARD = "FORWARD"
ACTION_BACKWARD = "BACKWARD"
ACTION_TURN_LEFT = "TURN_LEFT"
ACTION_TURN_RIGHT = "TURN_RIGHT"
ACTION_STOP = "STOP"


class CmdVelCarWebBridge(Node):
    def __init__(self) -> None:
        super().__init__("cmd_vel_car_web_bridge")

        # Deadzone below which linear.x / angular.z are treated as zero.
        # Keeps STOP stable against tiny numerical noise from teleop / joy.
        self.declare_parameter("deadzone", 0.05)

        self._sub = self.create_subscription(
            Twist, "/cmd_vel", self._on_cmd_vel, 10
        )
        self._pub = self.create_publisher(
            String, "/vehicle/control_action", 10
        )

        self._last_action: str | None = None

        self.get_logger().info(
            "cmd_vel_car_web_bridge started (dry-run, no car_web call). "
            "Subscribing /cmd_vel, publishing /vehicle/control_action."
        )

    def _deadzone(self) -> float:
        return float(self.get_parameter("deadzone").value)

    def _map_twist(self, msg: Twist) -> str:
        # Priority: forward/backward beats turning. Mixed Twist is reduced
        # to pure linear action in this dry-run stage on purpose.
        dz = self._deadzone()
        lx = msg.linear.x
        az = msg.angular.z

        if lx > dz:
            return ACTION_FORWARD
        if lx < -dz:
            return ACTION_BACKWARD
        if az > dz:
            return ACTION_TURN_LEFT
        if az < -dz:
            return ACTION_TURN_RIGHT
        return ACTION_STOP

    def _on_cmd_vel(self, msg: Twist) -> None:
        action = self._map_twist(msg)

        # Log every incoming cmd_vel so a live ros2 run tail is useful,
        # but only emit at INFO level when the action changes to avoid
        # spamming when a teleop is pumping the same Twist at high rate.
        if action != self._last_action:
            self.get_logger().info(f"CONTROL_ACTION={action}")
            self._last_action = action
        else:
            self.get_logger().debug(f"CONTROL_ACTION={action}")

        out = String()
        out.data = action
        self._pub.publish(out)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = CmdVelCarWebBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
