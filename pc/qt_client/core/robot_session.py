from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from core.robot_state import RobotConnectionState

_MAX_LINEAR = 0.50
_MAX_ANGULAR = 1.00


class RobotSession(QObject):
    """Robot control session; emits JSON gateway telemetry for UI layers."""

    odom_updated = pyqtSignal(object)
    base_status_updated = pyqtSignal(object)
    gateway_connection_changed = pyqtSignal(bool, str)

    def __init__(self, profile, backend, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.backend = backend
        self.state = RobotConnectionState.DISCONNECTED
        self.last_error = ""
        self.manual_control_enabled = True
        self.last_odom: Optional[Dict[str, Any]] = None
        self.last_base_status: Optional[Dict[str, Any]] = None
        self._bind_backend_feedback()

    def _bind_backend_feedback(self) -> None:
        bind = getattr(self.backend, "bind_feedback", None)
        if callable(bind):
            bind(
                on_message=self._handle_json_message,
                on_connection=self._handle_gateway_connection,
            )

    def _handle_json_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "odom_base":
            self.last_odom = msg
            self.odom_updated.emit(msg)
        elif msg_type == "base_status":
            self.last_base_status = msg
            self.base_status_updated.emit(msg)

    def _handle_gateway_connection(self, ok: bool, detail: str) -> None:
        self.gateway_connection_changed.emit(ok, detail)
        if not ok:
            self.last_error = detail or "JSON 网关连接中断"

    def connect(self) -> bool:
        self.state = RobotConnectionState.CONNECTING
        try:
            self.backend.connect(self.profile)
            self.state = RobotConnectionState.CONNECTED
            self.last_error = ""
            self.manual_control_enabled = True
            return True
        except Exception as exc:
            self.state = RobotConnectionState.FAILED
            self.last_error = str(exc)
            print("RobotSession connect failed:", self.last_error)
            return False

    def disconnect(self) -> None:
        self.backend.disconnect()
        self.state = RobotConnectionState.DISCONNECTED

    def cleanup(self) -> None:
        unbind = getattr(self.backend, "unbind_feedback", None)
        if callable(unbind):
            unbind(
                on_message=self._handle_json_message,
                on_connection=self._handle_gateway_connection,
            )
        self.backend.cleanup()
        self.state = RobotConnectionState.DISCONNECTED

    def is_connected(self) -> bool:
        return self.state == RobotConnectionState.CONNECTED and self.backend.is_connected()

    def send_velocity(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> bool:
        if not self.is_connected():
            self.last_error = "not connected; velocity rejected"
            print("RobotSession velocity rejected:", self.last_error)
            return False
        if not self.manual_control_enabled:
            self.last_error = "manual control disabled"
            print("RobotSession velocity rejected:", self.last_error)
            return False

        lx = max(-_MAX_LINEAR, min(_MAX_LINEAR, float(linear_x)))
        ly = max(-_MAX_LINEAR, min(_MAX_LINEAR, float(linear_y)))
        az = max(-_MAX_ANGULAR, min(_MAX_ANGULAR, float(angular_z)))

        try:
            print("RobotSession velocity:", f"lx={lx:.3f} ly={ly:.3f} az={az:.3f}")
            self.backend.send_velocity(lx, ly, az)
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            print("RobotSession velocity failed:", self.last_error)
            return False

    def stop_motion(self) -> bool:
        if not self.is_connected():
            print("RobotSession stop ignored: not connected")
            return False
        try:
            print("RobotSession stop_motion")
            self.backend.stop_motion()
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            print("RobotSession stop_motion failed:", self.last_error)
            return False

    def emergency_stop(self) -> bool:
        self.manual_control_enabled = False
        if not self.is_connected():
            print("RobotSession emergency_stop ignored: not connected")
            return False
        try:
            print("RobotSession emergency_stop")
            self.backend.emergency_stop()
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            print("RobotSession emergency_stop failed:", self.last_error)
            return False
