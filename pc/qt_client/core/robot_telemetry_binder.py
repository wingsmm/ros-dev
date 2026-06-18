from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt5.QtCore import QObject

from core.robot_state import RobotConnectionState
from gateway.json_telemetry import format_connection_detail

if TYPE_CHECKING:
    from core.robot_session import RobotSession
    from ui.widgets.robot_hud_bar import RobotHudBar
    from ui.widgets.robot_telemetry_panel import RobotTelemetryPanel


class RobotTelemetryBinder(QObject):
    """Bind RobotSession JSON feedback to shared HUD and optional detail panels."""

    def __init__(self, session: "RobotSession", robot_name: str, parent=None):
        super().__init__(parent)
        self._session = session
        self._robot_name = robot_name
        self._hud: Optional[RobotHudBar] = None
        self._panels: list[RobotTelemetryPanel] = []

        session.odom_updated.connect(self._on_odom)
        session.base_status_updated.connect(self._on_base_status)
        session.gateway_connection_changed.connect(self._on_gateway_connection)

    def bind_hud(self, hud: "RobotHudBar") -> None:
        self._hud = hud

    @property
    def session(self) -> "RobotSession":
        return self._session

    def register_panel(self, panel: "RobotTelemetryPanel") -> None:
        if panel not in self._panels:
            self._panels.append(panel)

    def unregister_panel(self, panel: "RobotTelemetryPanel") -> None:
        if panel in self._panels:
            self._panels.remove(panel)

    def replay(self) -> None:
        self.refresh_connection()
        if self._session.last_odom is not None:
            self._on_odom(self._session.last_odom)
        if self._session.last_base_status is not None:
            self._on_base_status(self._session.last_base_status)

    def refresh_connection(self) -> None:
        if self._hud is None:
            return
        session = self._session
        if session.is_connected():
            detail = self._robot_name
            if session.last_base_status is not None:
                detail = format_connection_detail(self._robot_name, session.last_base_status)
            self._hud.set_connection(True, detail)
        elif session.state == RobotConnectionState.FAILED:
            self._hud.set_connection(False, session.last_error or "连接失败")
        else:
            self._hud.set_connection(False, self._robot_name)

    def _on_odom(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        from gateway.json_telemetry import format_odom_display

        view = format_odom_display(msg)
        if self._hud is not None:
            self._hud.set_motion(view.linear_hud, view.angular_hud)
            self._hud.set_pose(view.pose_summary)
        for panel in self._panels:
            panel.update_odom(msg)

    def _on_base_status(self, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        for panel in self._panels:
            panel.update_base_status(msg)
        if self._hud is not None and self._session.is_connected():
            self._hud.set_connection(
                True, format_connection_detail(self._robot_name, msg)
            )

    def _on_gateway_connection(self, ok: bool, detail: str) -> None:
        if ok:
            self.refresh_connection()
            return
        if self._hud is not None:
            self._hud.set_connection(False, detail or "JSON 网关断开")
            self._hud.set_motion("--", "--")
            self._hud.set_pose("--")
        for panel in self._panels:
            panel.clear()
