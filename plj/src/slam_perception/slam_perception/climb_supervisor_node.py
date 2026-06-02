from __future__ import annotations

from enum import Enum
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool, Float32MultiArray, String


class ClimbState(str, Enum):
    NORMAL = "normal"
    STOPPING = "stopping"
    WAITING_CHASSIS = "waiting_chassis"
    CLIMBING = "climbing"
    RECOVERING = "recovering"


class ClimbSupervisor(Node):
    """State machine that turns stable stair detections into chassis mode commands."""

    def __init__(self) -> None:
        super().__init__("climb_supervisor")
        self._declare_parameters()
        self._load_parameters()

        self.state = ClimbState.NORMAL
        self.state_started = self.get_clock().now()
        self.last_info: Optional[list[float]] = None
        self.climb_ready = False
        self.climb_complete = False

        self.create_subscription(Bool, self.stair_detected_topic, self._on_stair_detected, 10)
        self.create_subscription(Float32MultiArray, self.stair_info_topic, self._on_stair_info, 10)
        self.create_subscription(Bool, self.climb_ready_topic, self._on_climb_ready, 10)
        self.create_subscription(Bool, self.climb_complete_topic, self._on_climb_complete, 10)

        self.cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.climb_trigger_pub = self.create_publisher(String, self.climb_trigger_topic, 10)
        self.normal_trigger_pub = self.create_publisher(String, self.normal_trigger_topic, 10)
        self.state_pub = self.create_publisher(String, self.state_topic, 10)
        self.localization_reinit_pub = self.create_publisher(
            String,
            self.localization_reinit_topic,
            10,
        )
        self.backend_pause_pub = self.create_publisher(Bool, self.backend_pause_topic, 10)

        self.create_timer(0.1, self._tick)
        self.get_logger().info("climb_supervisor ready")

    def _declare_parameters(self) -> None:
        defaults = {
            "stair_detected_topic": "/stair_detected",
            "stair_info_topic": "/stair_info",
            "climb_ready_topic": "/climb_ready",
            "climb_complete_topic": "/climb_complete",
            "cmd_vel_topic": "/cmd_vel",
            "climb_trigger_topic": "/climb_mode_trigger",
            "normal_trigger_topic": "/normal_mode_trigger",
            "state_topic": "/climb_state",
            "localization_reinit_topic": "/localization_reinit",
            "backend_pause_topic": "/slam_backend_pause",
            "max_climbable_height": 0.25,
            "min_confidence": 0.60,
            "stop_before_climb_sec": 0.8,
            "chassis_ready_timeout_sec": 5.0,
            "climb_timeout_sec": 20.0,
            "recovery_sec": 2.0,
            "auto_trigger": False,
            "publish_stop_command": True,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_parameters(self) -> None:
        for name in (
            "stair_detected_topic",
            "stair_info_topic",
            "climb_ready_topic",
            "climb_complete_topic",
            "cmd_vel_topic",
            "climb_trigger_topic",
            "normal_trigger_topic",
            "state_topic",
            "localization_reinit_topic",
            "backend_pause_topic",
        ):
            setattr(self, name, self.get_parameter(name).get_parameter_value().string_value)

        for name in (
            "max_climbable_height",
            "min_confidence",
            "stop_before_climb_sec",
            "chassis_ready_timeout_sec",
            "climb_timeout_sec",
            "recovery_sec",
        ):
            setattr(self, name, self.get_parameter(name).get_parameter_value().double_value)

        for name in ("auto_trigger", "publish_stop_command"):
            setattr(self, name, self.get_parameter(name).get_parameter_value().bool_value)

    def _on_stair_info(self, msg: Float32MultiArray) -> None:
        if len(msg.data) >= 5:
            self.last_info = list(msg.data[:5])

    def _on_stair_detected(self, msg: Bool) -> None:
        if not msg.data or self.state != ClimbState.NORMAL:
            return
        if not self.auto_trigger:
            return
        if not self._last_info_is_climbable():
            return
        self.climb_ready = False
        self.climb_complete = False
        self._transition(ClimbState.STOPPING)

    def _on_climb_ready(self, msg: Bool) -> None:
        self.climb_ready = msg.data

    def _on_climb_complete(self, msg: Bool) -> None:
        self.climb_complete = msg.data

    def _tick(self) -> None:
        self.state_pub.publish(String(data=self.state.value))
        if self.publish_stop_command and self.state in (
            ClimbState.STOPPING,
            ClimbState.WAITING_CHASSIS,
            ClimbState.RECOVERING,
        ):
            self.cmd_vel_pub.publish(Twist())

        elapsed = self._elapsed_in_state()
        if self.state == ClimbState.STOPPING and elapsed >= self.stop_before_climb_sec:
            self.backend_pause_pub.publish(Bool(data=True))
            self._publish_mode_command(self.climb_trigger_pub, "climb")
            self._transition(ClimbState.WAITING_CHASSIS)
        elif self.state == ClimbState.WAITING_CHASSIS:
            if self.climb_ready:
                self._transition(ClimbState.CLIMBING)
            elif elapsed >= self.chassis_ready_timeout_sec:
                self.get_logger().error("climb_ready timeout, aborting climb")
                self.backend_pause_pub.publish(Bool(data=False))
                self._publish_mode_command(self.normal_trigger_pub, "normal")
                self.climb_ready = False
                self.climb_complete = False
                self._transition(ClimbState.NORMAL)
        elif self.state == ClimbState.CLIMBING:
            if self.climb_complete or elapsed >= self.climb_timeout_sec:
                self._publish_mode_command(self.normal_trigger_pub, "normal")
                self.backend_pause_pub.publish(Bool(data=False))
                self.localization_reinit_pub.publish(String(data="relocalize_after_climb"))
                self._transition(ClimbState.RECOVERING)
        elif self.state == ClimbState.RECOVERING and elapsed >= self.recovery_sec:
            self.climb_ready = False
            self.climb_complete = False
            self._transition(ClimbState.NORMAL)

    def _last_info_is_climbable(self) -> bool:
        if self.last_info is None:
            return False
        detected, height, _distance, _width, confidence = self.last_info
        return (
            detected > 0.5
            and height <= self.max_climbable_height
            and confidence >= self.min_confidence
        )

    def _transition(self, state: ClimbState) -> None:
        if self.state == state:
            return
        self.get_logger().info(f"climb state: {self.state.value} -> {state.value}")
        self.state = state
        self.state_started = self.get_clock().now()

    def _elapsed_in_state(self) -> float:
        return (self.get_clock().now() - self.state_started).nanoseconds / 1e9

    def _publish_mode_command(self, publisher, mode: str) -> None:
        height = self.last_info[1] if self.last_info else 0.0
        distance = self.last_info[2] if self.last_info else 0.0
        publisher.publish(String(data=f"{mode} height={height:.3f} distance={distance:.3f}"))


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = ClimbSupervisor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
