from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication

from core.robot_state import RobotConnectionState
from core.warning_controller import WarningController, WarningSettings
from core.laser_scan_frame import LaserScanFrame
from core.odom_session_origin import OdomSessionOrigin
from core.odom_telemetry_logger import maybe_log_odom, reset_odom_telemetry_log

_MAX_LINEAR = 0.50
_MAX_ANGULAR = 1.00

logger = logging.getLogger(__name__)


class RobotSession(QObject):
    """Robot control session; emits JSON gateway telemetry for UI layers."""

    odom_updated = pyqtSignal(object)
    odom_raw_updated = pyqtSignal(object)
    odom_laser_updated = pyqtSignal(object)
    base_status_updated = pyqtSignal(object)
    warning_updated = pyqtSignal(object)
    laser_scan_updated = pyqtSignal(object)
    gateway_connection_changed = pyqtSignal(bool, str)

    def __init__(self, profile, backend, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.backend = backend
        self.state = RobotConnectionState.DISCONNECTED
        self.last_error = ""
        self.manual_control_enabled = True
        self.last_odom: Optional[Dict[str, Any]] = None
        self.last_odom_raw: Optional[Dict[str, Any]] = None
        self.last_odom_laser: Optional[Dict[str, Any]] = None
        self.last_base_status: Optional[Dict[str, Any]] = None
        self.last_warning: Optional[Dict[str, Any]] = None
        self.last_laser_scan: Optional[Any] = None
        self._odom_origin = OdomSessionOrigin()
        self._warning = WarningController(self._warning_settings_from_profile())
        self._warning_timer = QTimer(self)
        self._warning_timer.setInterval(100)
        self._warning_timer.timeout.connect(self._on_warning_timer)
        self._warning_timer.start()
        self._bind_backend_feedback()

    def _warning_settings_from_profile(self) -> WarningSettings:
        profile = self.profile
        return WarningSettings(
            enabled=bool(getattr(profile, "warning_enabled", False)),
            safemode=bool(getattr(profile, "warning_safemode", True)),
            beep=bool(getattr(profile, "warning_beep", True)),
            min_distance_m=float(getattr(profile, "warning_min_distance", 3.0)),
            front_half_angle_deg=float(
                getattr(profile, "warning_front_half_angle", 40.0)
            ),
            min_valid_range_m=float(
                getattr(profile, "warning_min_valid_range", 0.25)
            ),
        )

    @property
    def warning_controller(self) -> WarningController:
        return self._warning

    def reload_warning_settings(self) -> None:
        self._warning.apply_settings(self._warning_settings_from_profile())
        settings = self._warning.settings
        logger.info(
            "warning config: enabled=%s safemode=%s min_distance=%.1f "
            "front_half=%.0f min_valid=%.2f",
            settings.enabled,
            settings.safemode,
            settings.min_distance_m,
            settings.front_half_angle_deg,
            settings.min_valid_range_m,
        )
        self._emit_warning_state()

    def report_front_scan_warning(
        self, front_min_m: float, *, stale: bool = False
    ) -> None:
        """Robot page feeds local /scan front-sector warning into shared state."""
        self._warning.on_scan_warning(front_min_m=front_min_m, stale=stale)
        if self._warning.should_beep():
            QApplication.beep()
        self._emit_warning_state()

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
            self._warning.on_odom(float(msg.get("linear_x", 0.0)))
            maybe_log_odom("odom_base", msg)
            self.odom_updated.emit(msg)
            self._emit_warning_state()
        elif msg_type == "odom_raw":
            self.last_odom_raw = msg
            maybe_log_odom("odom_raw", msg)
            self.odom_raw_updated.emit(msg)
        elif msg_type == "odom_laser":
            self.last_odom_laser = msg
            maybe_log_odom("odom_laser", msg)
            self.odom_laser_updated.emit(msg)
        elif msg_type == "base_status":
            self.last_base_status = msg
            self.base_status_updated.emit(msg)
        elif msg_type == "laser_scan":
            frame = LaserScanFrame.from_message(
                msg,
                reverse=bool(getattr(self.profile, "reverse_laser_scan", False)),
            )
            if frame is None:
                return
            self.last_laser_scan = frame
            self.laser_scan_updated.emit(frame)

    def _on_warning_timer(self) -> None:
        before = self._warning.warn_amount
        became_stale = self._warning.touch_scan_timeout()
        if self.last_odom is not None:
            self._warning.on_odom(float(self.last_odom.get("linear_x", 0.0)))
        if became_stale or before != self._warning.warn_amount:
            self._emit_warning_state()

    def _emit_warning_state(self) -> None:
        scale = self._warning.forward_scale(1.0)
        payload = {
            "warn_amount": self._warning.warn_amount,
            "scan_stale": self._warning.scan_stale,
            "enabled": self._warning.settings.enabled,
            "safemode": self._warning.settings.safemode,
            "front_min_m": self._warning.front_min_m,
            "forward_scale": scale,
            "threshold_m": self._warning.warning_threshold_m,
        }
        self.last_warning = payload
        self.warning_updated.emit(payload)

    def _handle_gateway_connection(self, ok: bool, detail: str) -> None:
        self.gateway_connection_changed.emit(ok, detail)
        if not ok:
            self.last_error = detail or "JSON 网关连接中断"

    def relative_odom_pose(
        self, msg: Dict[str, Any]
    ) -> Tuple[float, float, float]:
        """Session-local pose (x/y/yaw aligned to first odom_base after connect)."""
        return self._odom_origin.relative_pose(msg)

    def odom_origin_summary(self) -> str:
        return self._odom_origin.format_summary()

    def odom_origin_is_set(self) -> bool:
        return self._odom_origin.is_set()

    def connect(self) -> bool:
        self.state = RobotConnectionState.CONNECTING
        self._odom_origin.reset()
        self.last_odom = None
        self.last_odom_raw = None
        self.last_odom_laser = None
        try:
            self.backend.connect(self.profile)
            self.state = RobotConnectionState.CONNECTED
            self.last_error = ""
            self.manual_control_enabled = True
            self.reload_warning_settings()
            return True
        except Exception as exc:
            self.state = RobotConnectionState.FAILED
            self.last_error = str(exc)
            logger.error("connect failed: %s", self.last_error)
            return False

    def disconnect(self) -> None:
        self.backend.disconnect()
        reset_odom_telemetry_log()
        self._odom_origin.reset()
        self.state = RobotConnectionState.DISCONNECTED

    def cleanup(self) -> None:
        self._warning_timer.stop()
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
            logger.warning("velocity rejected: %s", self.last_error)
            return False
        if not self.manual_control_enabled:
            self.last_error = "manual control disabled"
            logger.warning("velocity rejected: %s", self.last_error)
            return False

        lx = max(-_MAX_LINEAR, min(_MAX_LINEAR, float(linear_x)))
        ly = max(-_MAX_LINEAR, min(_MAX_LINEAR, float(linear_y)))
        az = max(-_MAX_ANGULAR, min(_MAX_ANGULAR, float(angular_z)))

        profile = self.profile
        if getattr(profile, "invert_x", False):
            lx = -lx
        if getattr(profile, "invert_y", False):
            ly = -ly
        if getattr(profile, "invert_angular_velocity", False):
            az = -az

        try:
            logger.debug(
                "velocity: lx=%.3f ly=%.3f az=%.3f",
                lx,
                ly,
                az,
            )
            self.backend.send_velocity(lx, ly, az)
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("velocity failed")
            return False

    def stop_motion(self) -> bool:
        if not self.is_connected():
            logger.debug("stop ignored: not connected")
            return False
        try:
            logger.info("stop_motion")
            self.backend.stop_motion()
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("stop_motion failed")
            return False

    def emergency_stop(self) -> bool:
        self.manual_control_enabled = False
        if not self.is_connected():
            logger.warning("emergency_stop ignored: not connected")
            return False
        try:
            logger.warning("emergency_stop")
            self.backend.emergency_stop()
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("emergency_stop failed")
            return False
