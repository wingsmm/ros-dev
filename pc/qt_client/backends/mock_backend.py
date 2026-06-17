from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

from backends.base import RobotBackend

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


class MockRobotBackend(RobotBackend):
    def __init__(self) -> None:
        self._connected = False
        self._last_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._emergency_stopped = False

    def connect(self, profile: RobotInfo) -> None:
        self._connected = True
        self._emergency_stopped = False

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_velocity(self) -> Tuple[float, float, float]:
        return self._last_velocity

    @property
    def emergency_stopped(self) -> bool:
        return self._emergency_stopped

    def send_velocity(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> None:
        self._last_velocity = (linear_x, linear_y, angular_z)
        print(
            "MOCK velocity:",
            f"lx={linear_x:.3f} ly={linear_y:.3f} az={angular_z:.3f}",
        )

    def stop_motion(self) -> None:
        self.send_velocity(0.0, 0.0, 0.0)

    def emergency_stop(self) -> None:
        self._emergency_stopped = True
        self.stop_motion()
        print("MOCK emergency_stop")
