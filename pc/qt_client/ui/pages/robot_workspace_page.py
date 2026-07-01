from __future__ import annotations

from typing import Dict, Optional

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QRect, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from core import RobotSession
from core.camera_controllers import CameraServices
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from ui.models.robot_info import RobotInfo
from ui.models.robot_store import RobotStore
from ui.pages.depth_camera_page import DepthCameraPage
from ui.pages.ground_perception_page import GroundPerceptionPage
from ui.pages.odom_compare_page import OdomComparePage
from ui.pages.placeholder_page import PlaceholderPage
from ui.pages.rgb_camera_page import RgbCameraPage
from ui.pages.robot_page import RobotPage
from ui.pages.settings_page import SettingsPage
from ui.widgets.robot_hud_bar import RobotHudBar
from ui.widgets.robot_side_nav import CONTENT_PAGE_IDS, RobotSideNav

_WORKSPACE_PLACEHOLDERS: Dict[str, str] = {
    "overview": "总览功能待接入",
    "slam_map": "SLAM 地图功能待接入",
    "gps_map": "GPS 地图功能待接入",
    "about": "关于功能待接入",
}

_NAV_TITLES: Dict[str, str] = {
    "overview": "总览",
    "camera": "摄像头",
    "depth_camera": "深度相机",
    "ground_perception": "地面感知",
    "robot": "2D 雷达",
    "odom_compare": "里程计对照",
    "slam_map": "SLAM 地图",
    "gps_map": "GPS 地图",
    "settings": "设置",
    "about": "关于",
}


class RobotWorkspacePage(QWidget):
    back_requested = pyqtSignal()

    def __init__(
        self,
        robot: RobotInfo,
        session: Optional[RobotSession] = None,
        robot_store: Optional[RobotStore] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.robot = robot
        self.session = session
        self._robot_store = robot_store
        self._nav_open = False
        self._nav_width = 320
        self._nav_anim: Optional[QPropertyAnimation] = None
        self._side_nav = RobotSideNav()
        self._scrim = QWidget(self)
        self._hud = RobotHudBar()
        self._stack = QStackedWidget()
        self._page_index: Dict[str, int] = {}
        self._active_page_id = ""
        self._telemetry_binder: Optional[RobotTelemetryBinder] = None
        self._ros2_bridge: Optional[Ros2BridgeManager] = None
        self._camera_services: Optional[CameraServices] = None
        if session is not None:
            self._telemetry_binder = RobotTelemetryBinder(session, robot.name, self)
            self._hud.stop_motion_requested.connect(self._on_hud_stop_motion)
            self._ros2_bridge = Ros2BridgeManager(
                session=session, robot=robot, parent=self
            )
            self._camera_services = CameraServices(
                robot=robot, ros2_bridge=self._ros2_bridge, parent=self
            )
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        main_col = QVBoxLayout()
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)
        main_col.addWidget(self._hud)

        if self._telemetry_binder is not None:
            self._telemetry_binder.bind_hud(self._hud)
        for page_id in CONTENT_PAGE_IDS:
            if page_id == "camera" and self._camera_services is not None:
                page = RgbCameraPage(
                    self.robot,
                    self._camera_services,
                    telemetry_binder=self._telemetry_binder,
                    ros2_bridge=self._ros2_bridge,
                )
            elif page_id == "depth_camera" and self._camera_services is not None:
                page = DepthCameraPage(
                    self.robot,
                    self._camera_services,
                    telemetry_binder=self._telemetry_binder,
                    ros2_bridge=self._ros2_bridge,
                )
            elif page_id == "ground_perception" and self._camera_services is not None:
                page = GroundPerceptionPage(
                    self.robot,
                    self._camera_services,
                    telemetry_binder=self._telemetry_binder,
                    ros2_bridge=self._ros2_bridge,
                )
            elif page_id == "robot":
                page = RobotPage(
                    self.robot,
                    telemetry_binder=self._telemetry_binder,
                    ros2_bridge=self._ros2_bridge,
                )
            elif page_id == "odom_compare":
                page = OdomComparePage(
                    self.robot, telemetry_binder=self._telemetry_binder
                )
            elif page_id == "settings" and self._robot_store is not None:
                page = SettingsPage(
                    self.robot,
                    self._robot_store,
                    session=self.session,
                )
                page.settings_saved.connect(self._on_settings_saved)
            else:
                title = _NAV_TITLES.get(page_id, page_id)
                hint = _WORKSPACE_PLACEHOLDERS.get(page_id, "功能待接入")
                page = PlaceholderPage(title, hint)
            self._page_index[page_id] = self._stack.addWidget(page)
        main_col.addWidget(self._stack, 1)

        content_row.addLayout(main_col, 1)
        root.addLayout(content_row, 1)

        self._scrim.setStyleSheet("background: rgba(0, 0, 0, 0.45);")
        self._scrim.hide()
        self._scrim.mousePressEvent = self._on_scrim_pressed  # type: ignore[method-assign]

        self._side_nav.setParent(self)
        self._side_nav.page_selected.connect(self._on_nav_selected)
        self._side_nav.hide()

        if self._telemetry_binder is not None:
            self._telemetry_binder.replay()
        else:
            self._hud.set_placeholder()

        self._show_content_page("overview")

    def _on_settings_saved(self) -> None:
        if self.session is not None:
            self.session.reload_warning_settings()
        if self._camera_services is not None:
            self._camera_services.refresh_robot(self.robot)
        for page_id in ("camera", "depth_camera", "ground_perception", "robot"):
            page = self._page_widget(page_id)
            if page is not None and hasattr(page, "refresh_robot_settings"):
                page.refresh_robot_settings()
        compare = self._page_widget("odom_compare")
        if compare is not None and hasattr(compare, "refresh_robot_settings"):
            compare.refresh_robot_settings()

    def _on_hud_stop_motion(self) -> None:
        if self.session is None:
            return
        self.session.stop_motion()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_layer_geometry()

    def _nav_rect(self, opened: bool) -> QRect:
        x = 0 if opened else -self._nav_width
        return QRect(x, 0, self._nav_width, self.height())

    def _scrim_rect(self) -> QRect:
        return QRect(
            self._nav_width,
            0,
            max(0, self.width() - self._nav_width),
            self.height(),
        )

    def _sync_layer_geometry(self) -> None:
        self._scrim.setGeometry(self._scrim_rect())
        self._side_nav.setGeometry(self._nav_rect(opened=self._nav_open))

    def _on_scrim_pressed(self, event) -> None:
        self.close_navigation()
        event.accept()

    def toggle_navigation(self) -> None:
        if self._nav_open:
            self.close_navigation()
        else:
            self.open_navigation()

    def open_navigation(self) -> None:
        if self._nav_open:
            return
        self._nav_open = True
        self._sync_layer_geometry()
        self._scrim.show()
        self._side_nav.show()
        self._scrim.raise_()
        self._side_nav.raise_()
        self._animate_navigation(opened=True)

    def close_navigation(self) -> None:
        if not self._nav_open:
            return
        self._nav_open = False
        self._animate_navigation(opened=False)

    def _animate_navigation(self, opened: bool) -> None:
        if self._nav_anim is not None:
            self._nav_anim.stop()
        self._nav_anim = QPropertyAnimation(self._side_nav, b"geometry", self)
        self._nav_anim.setDuration(180)
        self._nav_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._nav_anim.setStartValue(self._side_nav.geometry())
        self._nav_anim.setEndValue(self._nav_rect(opened))
        if not opened:
            self._nav_anim.finished.connect(self._after_navigation_closed)
        self._nav_anim.start()

    def _after_navigation_closed(self) -> None:
        if self._nav_open:
            return
        self._side_nav.hide()
        self._scrim.hide()

    def _on_nav_selected(self, page_id: str) -> None:
        if page_id == "back":
            self.back_requested.emit()
            return
        self._show_content_page(page_id)
        self.close_navigation()

    def _page_widget(self, page_id: str) -> Optional[QWidget]:
        index = self._page_index.get(page_id)
        if index is None:
            return None
        return self._stack.widget(index)

    def _notify_page_lifecycle(self, page_id: str, *, entering: bool) -> None:
        widget = self._page_widget(page_id)
        if widget is None:
            return
        method = "on_page_activated" if entering else "on_page_deactivated"
        handler = getattr(widget, method, None)
        if callable(handler):
            handler()

    def shutdown(self) -> None:
        if self._active_page_id:
            self._notify_page_lifecycle(self._active_page_id, entering=False)
            self._active_page_id = ""
        for i in range(self._stack.count()):
            widget = self._stack.widget(i)
            if hasattr(widget, "shutdown"):
                widget.shutdown()
        if self._camera_services is not None:
            self._camera_services.shutdown()
            self._camera_services = None
        if self._ros2_bridge is not None:
            self._ros2_bridge.shutdown()
            self._ros2_bridge = None

    def _show_content_page(self, page_id: str) -> None:
        if page_id == self._active_page_id:
            return
        if self._active_page_id:
            self._notify_page_lifecycle(self._active_page_id, entering=False)
        index = self._page_index.get(page_id)
        if index is None:
            return
        self._stack.setCurrentIndex(index)
        self._side_nav.set_active(page_id)
        self._active_page_id = page_id
        self._notify_page_lifecycle(page_id, entering=True)
        if self._telemetry_binder is not None:
            self._telemetry_binder.replay()
