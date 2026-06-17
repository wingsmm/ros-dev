from __future__ import annotations

from core.robot_state import RobotConnectionState


class RobotSession:
    def __init__(self, profile, backend):
        self.profile = profile
        self.backend = backend
        self.state = RobotConnectionState.DISCONNECTED
        self.last_error = ""

    def connect(self) -> bool:
        self.state = RobotConnectionState.CONNECTING
        try:
            self.backend.connect(self.profile)
            self.state = RobotConnectionState.CONNECTED
            self.last_error = ""
            return True
        except Exception as exc:
            self.state = RobotConnectionState.FAILED
            self.last_error = str(exc)
            return False

    def disconnect(self) -> None:
        self.backend.disconnect()
        self.state = RobotConnectionState.DISCONNECTED

    def cleanup(self) -> None:
        self.backend.cleanup()
