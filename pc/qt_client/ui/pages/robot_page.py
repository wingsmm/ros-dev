from __future__ import annotations

import logging
import math
import time
from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from core.laser_scan_frame import LaserScanFrame
from core.robot_frames import LASER_X, LASER_Y, LASER_YAW
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from core.ros2_runtime import auto_bridge_enabled
from core.warning_scan_math import compute_front_min_hit
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.laser_scan_view import LaserScanView, LaserToolbar
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.ros2_rviz_panel import Ros2RvizPanel

logger = logging.getLogger(__name__)
_SAFE_MODE_LOG_INTERVAL_SEC = 2.0


class RobotPage(QWidget):
    def __init__(
        self,
        robot: RobotInfo,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        ros2_bridge: Optional[Ros2BridgeManager] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._binder = telemetry_binder
        self._toolbar = LaserToolbar()
        self._laser_view = LaserScanView()
        self._ros2_panel = Ros2RvizPanel()
        self._manual = ManualControlStrip()
        self._warn_scan_logged = False
        self._last_safemode_log_mono = 0.0
        self._last_warning_hit_angle = float("nan")
        self._last_warning_scan_log_mono = 0.0
        session = self._binder.session if self._binder is not None else None
        self._ros2_bridge = ros2_bridge
        if self._ros2_bridge is not None:
            self._ros2_panel.set_manager(self._ros2_bridge)
        self._build_ui()
        self._wire_signals()
        self._apply_manual_speed_defaults()

        if session is not None:
            session.laser_scan_updated.connect(self._on_laser_scan_updated)
            if session.last_laser_scan is not None:
                self._on_laser_scan_updated(session.last_laser_scan)
            session.odom_updated.connect(self._on_odom_updated)
            if session.last_odom is not None:
                self._on_odom_updated(session.last_odom)
            session.warning_updated.connect(self._on_warning_updated)
            session.gateway_connection_changed.connect(self._on_gateway_connection)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        root.addWidget(self._toolbar)
        root.addWidget(self._laser_view, 1)
        root.addWidget(self._ros2_panel)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        self._toolbar.center_requested.connect(self._laser_view.center_view)
        self._toolbar.heading_lock_changed.connect(self._laser_view.set_heading_locked)
        self._laser_view.set_heading_locked(self._toolbar.is_heading_locked())

        self._manual.velocity_requested.connect(self._on_velocity_requested)
        self._manual.stop_requested.connect(self._on_stop_requested)

    def _apply_manual_speed_defaults(self) -> None:
        linear, angular = effective_manual_speeds(self._robot)
        self._manual.set_speeds(linear=linear, angular=angular)
        self._laser_view.set_scan_detail(self._robot.laser_scan_detail)

    def refresh_robot_settings(self) -> None:
        self._apply_manual_speed_defaults()
        session = self._binder.session if self._binder is not None else None
        if session is not None and session.last_laser_scan is not None:
            self._on_laser_scan_updated(session.last_laser_scan)
        elif session is not None:
            self._sync_warning_sector(
                session, stale=session.warning_controller.scan_stale
            )

    def _on_laser_scan_updated(self, frame: object) -> None:
        if not isinstance(frame, LaserScanFrame):
            return
        self._laser_view.update_scan(frame)
        session = self._binder.session if self._binder is not None else None
        if session is None:
            return

        settings = session.warning_controller.settings
        if not settings.enabled:
            self._sync_warning_sector(session, stale=False)
            return

        half_rad = math.radians(settings.front_half_angle_deg)
        front_min, hit_angle = compute_front_min_hit(
            frame.ranges,
            frame.angle_min,
            frame.angle_increment,
            min_valid_range=settings.min_valid_range_m,
            front_half_angle_rad=half_rad,
            yaw_offset_rad=LASER_YAW,
            x_offset_m=LASER_X,
            y_offset_m=LASER_Y,
        )
        stale = self._laser_view.is_scan_stale()
        session.report_front_scan_warning(front_min, stale=stale)

        if not self._warn_scan_logged and math.isfinite(front_min):
            logger.info("warning scan active: front_min=%.2f", front_min)
            self._warn_scan_logged = True
        self._log_warning_scan_sample(session, front_min, hit_angle, stale)

        self._last_warning_hit_angle = hit_angle
        self._sync_warning_sector(session, stale=stale)

    def _log_warning_scan_sample(
        self,
        session,
        front_min: float,
        hit_angle: float,
        stale: bool,
    ) -> None:
        now = time.monotonic()
        if now - self._last_warning_scan_log_mono < 2.0:
            return
        self._last_warning_scan_log_mono = now
        warning = session.warning_controller
        logger.info(
            "warning scan sample: front=%.2f hit_angle=%.1fdeg threshold=%.2f "
            "half=%.1fdeg warn=%.2f scale=%.2f stale=%s",
            front_min,
            math.degrees(hit_angle) if math.isfinite(hit_angle) else float("nan"),
            warning.warning_threshold_m,
            warning.settings.front_half_angle_deg,
            warning.warn_amount,
            warning.forward_scale(1.0),
            stale,
        )

    def _on_warning_updated(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        session = self._binder.session if self._binder is not None else None
        if session is None:
            return
        self._sync_warning_sector(
            session,
            stale=bool(msg.get("scan_stale", False)),
        )

    def _sync_warning_sector(
        self,
        session,
        *,
        stale: bool = False,
    ) -> None:
        settings = session.warning_controller.settings
        warning = session.warning_controller
        if not settings.enabled or stale:
            self._laser_view.set_warning_sector(False)
            return
        self._laser_view.set_warning_sector(
            True,
            half_angle_rad=math.radians(settings.front_half_angle_deg),
            min_distance_m=settings.min_distance_m,
            front_min_m=warning.front_min_m,
            warn_amount=warning.warn_amount,
            hit_angle_rad=self._last_warning_hit_angle,
        )

    def _on_odom_updated(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        session = self._binder.session if self._binder is not None else None
        if session is None:
            return
        relative_x, relative_y, yaw = session.relative_odom_pose(msg)
        self._laser_view.set_odom(relative_x, relative_y, yaw)

    def _on_gateway_connection(self, ok: bool, _detail: str) -> None:
        self._ros2_panel.refresh_display()
        if ok:
            self._maybe_auto_start_bridge()

    def _maybe_auto_start_bridge(self) -> None:
        if self._ros2_bridge is None or not auto_bridge_enabled():
            return
        session = self._binder.session if self._binder is not None else None
        if session is None or not session.is_connected():
            return
        if not self._ros2_bridge.snapshot().bridge_running:
            self._ros2_bridge.start_bridge()

    def on_page_activated(self) -> None:
        if self._binder is not None:
            self._binder.replay()
        self._laser_view.set_repaint_enabled(True)
        self._laser_view.replay_last_scan()
        self._apply_manual_speed_defaults()
        self._manual.set_keyboard_enabled(True)
        self._ros2_panel.refresh_display()
        self._maybe_auto_start_bridge()
        session = self._binder.session if self._binder is not None else None
        if session is not None:
            self._sync_warning_sector(
                session, stale=session.warning_controller.scan_stale
            )

    def on_page_deactivated(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._laser_view.set_repaint_enabled(False)

    def shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        session = self._binder.session if self._binder is not None else None
        if session is not None:
            try:
                session.laser_scan_updated.disconnect(self._on_laser_scan_updated)
            except TypeError:
                pass
            try:
                session.odom_updated.disconnect(self._on_odom_updated)
            except TypeError:
                pass
            try:
                session.warning_updated.disconnect(self._on_warning_updated)
            except TypeError:
                pass
            try:
                session.gateway_connection_changed.disconnect(
                    self._on_gateway_connection
                )
            except TypeError:
                pass
            session.stop_motion()
        self._laser_view.set_repaint_enabled(False)

    def _on_velocity_requested(self, lx: float, ly: float, az: float) -> None:
        if self._binder is None:
            return
        session = self._binder.session
        warning = session.warning_controller
        effective_lx = -lx if getattr(session.profile, "invert_x", False) else lx
        scale = warning.forward_scale(effective_lx)
        safe_lx = lx * scale
        if scale < 1.0 and effective_lx >= 0.0:
            now = time.monotonic()
            if now - self._last_safemode_log_mono >= _SAFE_MODE_LOG_INTERVAL_SEC:
                self._last_safemode_log_mono = now
                logger.info(
                    "SafeMode clipped vx %.3f -> %.3f front=%.2f warn=%.2f",
                    lx,
                    safe_lx,
                    warning.front_min_m,
                    warning.warn_amount,
                )
        session.send_velocity(safe_lx, ly, az)

    def _on_stop_requested(self) -> None:
        if self._binder is not None:
            self._binder.session.stop_motion()
