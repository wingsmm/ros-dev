from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from core.laser_scan_frame import LaserScanFrame
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from core.ros2_runtime import auto_bridge_enabled
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.laser_scan_view import LaserScanView, LaserToolbar
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.ros2_rviz_panel import Ros2RvizPanel


class RobotPage(QWidget):
    def __init__(
        self,
        robot: RobotInfo,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._binder = telemetry_binder
        self._toolbar = LaserToolbar()
        self._laser_view = LaserScanView()
        self._ros2_panel = Ros2RvizPanel()
        self._manual = ManualControlStrip()
        session = self._binder.session if self._binder is not None else None
        self._ros2_bridge = Ros2BridgeManager(session=session, parent=self)
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

    def _on_laser_scan_updated(self, frame: object) -> None:
        if isinstance(frame, LaserScanFrame):
            self._laser_view.update_scan(frame)

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
        if not auto_bridge_enabled():
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

    def on_page_deactivated(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._laser_view.set_repaint_enabled(False)

    def shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._ros2_bridge.shutdown()
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
        self._binder.session.send_velocity(lx, ly, az)

    def _on_stop_requested(self) -> None:
        if self._binder is not None:
            self._binder.session.stop_motion()
