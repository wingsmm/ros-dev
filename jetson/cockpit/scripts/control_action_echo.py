#!/usr/bin/env python3
"""Echo /vehicle/control_action from the Jetson dry-run bridge."""

from __future__ import annotations

import rclpy
from std_msgs.msg import String


def main() -> int:
    rclpy.init()
    node = rclpy.create_node("jetson_cockpit_control_action_echo")

    def on_msg(msg: String) -> None:
        print("CONTROL_ACTION=%s" % msg.data, flush=True)

    node.create_subscription(String, "/vehicle/control_action", on_msg, 10)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
