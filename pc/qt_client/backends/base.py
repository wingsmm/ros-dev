from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


class RobotBackend(ABC):
    @abstractmethod
    def connect(self, profile: RobotInfo) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    def send_velocity(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> None:
        self.send_cmd_vel(linear_x, linear_y, angular_z)

    def send_cmd_vel(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> None:
        raise NotImplementedError

    def stop_motion(self) -> None:
        self.send_velocity(0.0, 0.0, 0.0)

    def emergency_stop(self) -> None:
        self.stop_motion()

    def cleanup(self) -> None:
        self.disconnect()
