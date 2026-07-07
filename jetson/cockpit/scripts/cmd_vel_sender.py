#!/usr/bin/env python3
"""Publish one dry-run /cmd_vel command from PC/WSL."""

from __future__ import annotations

import argparse
import time

import rclpy
from geometry_msgs.msg import Twist

ACTIONS = {
    "forward": (1.0, 0.0),
    "backward": (-1.0, 0.0),
    "left": (0.0, 1.0),
    "right": (0.0, -1.0),
    "stop": (0.0, 0.0),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("--settle-ms", type=int, default=200)
    parser.add_argument(
        "--wait-subs",
        type=float,
        default=2.0,
        help="Seconds to wait for at least one subscriber before publishing. "
             "DDS discovery on WSL loopback is not instantaneous; publishing "
             "before a subscriber is known will silently drop the message.",
    )
    args = parser.parse_args()

    linear_x, angular_z = ACTIONS[args.action]
    rclpy.init()
    node = rclpy.create_node("jetson_cockpit_cmd_vel_sender")
    pub = node.create_publisher(Twist, "/cmd_vel", 10)
    try:
        deadline = time.monotonic() + max(0.0, args.wait_subs)
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if pub.get_subscription_count() > 0:
                break
        msg = Twist()
        msg.linear.x = linear_x
        msg.angular.z = angular_z
        pub.publish(msg)
        end = time.monotonic() + max(0.0, args.settle_ms / 1000.0)
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.02)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
