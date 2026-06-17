from __future__ import annotations

from typing import TYPE_CHECKING

from backends.base import RobotBackend
from backends.mock_backend import MockRobotBackend

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


def create_backend(profile: RobotInfo) -> RobotBackend:
    backend_type = profile.backend_type or "mock"
    if backend_type == "mock":
        return MockRobotBackend()
    if backend_type == "json_gateway":
        from backends.json_gateway_backend import JsonGatewayBackend

        return JsonGatewayBackend()
    if backend_type == "ros1_gateway":
        from backends.ros1_gateway_backend import Ros1GatewayBackend

        return Ros1GatewayBackend()
    if backend_type == "ros2_native":
        from backends.ros2_native_backend import Ros2NativeBackend

        return Ros2NativeBackend()
    raise ValueError(f"Unsupported backend type: {backend_type}")


__all__ = ["RobotBackend", "MockRobotBackend", "create_backend"]
