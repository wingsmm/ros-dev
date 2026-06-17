from __future__ import annotations

from typing import TYPE_CHECKING

from backends.base import RobotBackend

if TYPE_CHECKING:
    from ui.models.robot_info import RobotInfo


class MockRobotBackend(RobotBackend):
    def __init__(self) -> None:
        self._connected = False

    def connect(self, profile: RobotInfo) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected
