from __future__ import annotations

from typing import TYPE_CHECKING

from backends.base import RobotBackend

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


class Ros1GatewayBackend(RobotBackend):
    """PC client connects to robot-side gateway, not ROS1 Master XML-RPC directly."""

    def __init__(self) -> None:
        self._connected = False
        self._gateway_uri = ""

    def connect(self, profile: RobotInfo) -> None:
        if not profile.gateway_uri:
            raise ValueError("ROS1 gateway URI is required")
        # Future: HTTP/WebSocket/JSON handshake with robot-side gateway.
        self._gateway_uri = profile.gateway_uri
        raise NotImplementedError("ROS1 gateway backend not implemented yet")

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def send_cmd_vel(self, linear_x: float, linear_y: float, angular_z: float) -> None:
        raise NotImplementedError
