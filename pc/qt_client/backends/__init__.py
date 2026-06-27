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
        raise NotImplementedError(
            "ros1_gateway is reserved for experiments and is not available"
        )
    if backend_type == "ros2_native":
        raise NotImplementedError(
            "ros2_native is reserved for future ROS2-native platforms and is not available"
        )
    raise ValueError(f"Unsupported backend type: {backend_type}")


__all__ = ["RobotBackend", "MockRobotBackend", "create_backend"]
