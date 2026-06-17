from __future__ import annotations

from typing import TYPE_CHECKING

from backends.base import RobotBackend

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


class Ros2NativeBackend(RobotBackend):
    """Lazy-loaded ROS2 backend; rclpy must not be imported at module level."""

    def __init__(self) -> None:
        self._connected = False
        self._node = None

    def connect(self, profile: RobotInfo) -> None:
        # Future: initialize rclpy node / publishers / subscribers on demand.
        raise NotImplementedError("ROS2 native backend not implemented yet")

    def disconnect(self) -> None:
        self._connected = False
        self._node = None

    def is_connected(self) -> bool:
        return self._connected

    def send_cmd_vel(self, linear_x: float, linear_y: float, angular_z: float) -> None:
        raise NotImplementedError
