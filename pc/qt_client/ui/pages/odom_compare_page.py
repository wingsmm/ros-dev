from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from core.odom_compare_controller import OdomCompareController
from core.robot_telemetry_binder import RobotTelemetryBinder
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.odom_compare_view import OdomCompareToolbar, OdomCompareView


class OdomComparePage(QWidget):
    def __init__(
        self,
        robot: RobotInfo,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._binder = telemetry_binder
        self._controller = OdomCompareController(self)
        self._toolbar = OdomCompareToolbar()
        self._view = OdomCompareView()
        self._manual = ManualControlStrip()
        self._ui_active = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._build_ui()
        self._wire_signals()
        self._apply_manual_speed_defaults()
        self._bind_session()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        root.addWidget(self._toolbar)
        root.addWidget(self._view, 1)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        self._toolbar.zero_requested.connect(self._controller.request_zero)
        self._toolbar.clear_requested.connect(self._controller.clear_trajectories)
        self._toolbar.center_requested.connect(self._view.center_view)
        self._toolbar.visibility_changed.connect(self._controller.set_visible)

        self._manual.velocity_requested.connect(self._on_velocity_requested)
        self._manual.stop_requested.connect(self._on_stop_requested)

    def _bind_session(self) -> None:
        session = self._binder.session if self._binder is not None else None
        if session is None:
            return
        session.odom_updated.connect(self._controller.on_odom_base)
        session.odom_raw_updated.connect(self._controller.on_odom_raw)
        session.odom_laser_updated.connect(self._controller.on_odom_laser)
        session.gateway_connection_changed.connect(self._on_gateway_connection)
        if session.last_odom is not None:
            self._controller.on_odom_base(session.last_odom)
        if session.last_odom_raw is not None:
            self._controller.on_odom_raw(session.last_odom_raw)
        if session.last_odom_laser is not None:
            self._controller.on_odom_laser(session.last_odom_laser)

    def _on_gateway_connection(self, ok: bool, _detail: str) -> None:
        if not ok:
            self._controller.reset_all()
            if self._ui_active:
                self._refresh_ui()

    def _apply_manual_speed_defaults(self) -> None:
        linear, angular = effective_manual_speeds(self._robot)
        self._manual.set_speeds(linear=linear, angular=angular)

    def refresh_robot_settings(self) -> None:
        self._apply_manual_speed_defaults()

    def _refresh_ui(self) -> None:
        if not self._ui_active:
            return
        snapshot = self._controller.snapshot()
        self._toolbar.update_snapshot(snapshot)
        self._view.update_snapshot(snapshot)

    def on_page_activated(self) -> None:
        self._ui_active = True
        if self._binder is not None:
            self._binder.replay()
        self._controller.try_auto_zero()
        self._view.set_repaint_enabled(True)
        self._refresh_timer.start()
        self._refresh_ui()
        self._apply_manual_speed_defaults()
        self._manual.set_keyboard_enabled(True)

    def on_page_deactivated(self) -> None:
        self._ui_active = False
        self._manual.set_keyboard_enabled(False)
        self._refresh_timer.stop()
        self._view.set_repaint_enabled(False)

    def shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._refresh_timer.stop()
        session = self._binder.session if self._binder is not None else None
        if session is not None:
            for signal, slot in (
                (session.odom_updated, self._controller.on_odom_base),
                (session.odom_raw_updated, self._controller.on_odom_raw),
                (session.odom_laser_updated, self._controller.on_odom_laser),
                (session.gateway_connection_changed, self._on_gateway_connection),
            ):
                try:
                    signal.disconnect(slot)
                except TypeError:
                    pass
            session.stop_motion()
        self._view.set_repaint_enabled(False)

    def _on_velocity_requested(self, lx: float, ly: float, az: float) -> None:
        if self._binder is None:
            return
        self._binder.session.send_velocity(lx, ly, az)

    def _on_stop_requested(self) -> None:
        if self._binder is not None:
            self._binder.session.stop_motion()
