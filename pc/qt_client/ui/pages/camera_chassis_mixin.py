"""Shared chassis widgets (telemetry + manual control) for camera-family pages."""

from __future__ import annotations

import logging
from typing import Optional

from core.camera_controllers import CameraServices
from core.robot_telemetry_binder import RobotTelemetryBinder
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.telemetry_details_strip import TelemetryDetailsStrip

logger = logging.getLogger(__name__)


class CameraChassisMixin:
    """Mixin: telemetry strip + manual control wired to session binder."""

    _binder: Optional[RobotTelemetryBinder]
    _robot: RobotInfo
    _services: CameraServices
    _telemetry: TelemetryDetailsStrip
    _manual: ManualControlStrip

    def _init_camera_chassis(
        self,
        robot: RobotInfo,
        services: CameraServices,
        telemetry_binder: Optional[RobotTelemetryBinder],
    ) -> None:
        self._robot = robot
        self._services = services
        self._binder = telemetry_binder
        self._telemetry = TelemetryDetailsStrip()
        self._manual = ManualControlStrip()
        if self._binder is not None:
            self._binder.register_panel(self._telemetry.telemetry_panel)
        self._apply_manual_speed_defaults()
        self._manual.velocity_requested.connect(self._on_chassis_velocity)
        self._manual.stop_requested.connect(self._on_chassis_stop)

    def _apply_manual_speed_defaults(self) -> None:
        linear, angular = effective_manual_speeds(self._robot)
        self._manual.set_speeds(linear=linear, angular=angular)

    def refresh_robot_settings(self) -> None:
        self._apply_manual_speed_defaults()

    def _on_chassis_activate(self) -> None:
        if self._binder is not None:
            self._binder.replay()
        self._apply_manual_speed_defaults()
        self._manual.set_keyboard_enabled(True)

    def _on_chassis_deactivate(self) -> None:
        self._manual.set_keyboard_enabled(False)

    def _on_chassis_shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        if self._binder is not None:
            self._binder.unregister_panel(self._telemetry.telemetry_panel)

    def _on_chassis_velocity(self, lx: float, ly: float, az: float) -> None:
        if self._binder is None:
            return
        try:
            self._binder.session.send_velocity(lx, ly, az)
            logger.info(
                "MANUAL_FLOW session_velocity_sent lx=%.3f ly=%.3f az=%.3f",
                lx,
                ly,
                az,
            )
        except Exception:
            logger.exception("manual velocity failed")

    def _on_chassis_stop(self) -> None:
        if self._binder is not None:
            self._binder.session.stop_motion()
            logger.info("MANUAL_FLOW session_stop_motion")
