from __future__ import annotations

from dataclasses import fields, replace
from typing import Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from ui.preference_edit_dialog import build_value_dialog, exec_value_dialog

from core import RobotSession
from ui import android_prefs_strings as S
from ui.assets import android_asset
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import (
    DEFAULT_MANUAL_ANGULAR,
    DEFAULT_MANUAL_LINEAR,
    MANUAL_ANGULAR_MAX,
    MANUAL_ANGULAR_MIN,
    MANUAL_LINEAR_MAX,
    MANUAL_LINEAR_MIN,
)
from ui.models.robot_store import RobotStore

_ACCENT = "#009688"
_UNAVAILABLE = "当前 Qt 后端尚未接入此项运行能力"


def _android_icon(name: str) -> QIcon:
    path = android_asset(name)
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap)


class AndroidSwitch(QWidget):
    """Material-style switch: rounded track + circular thumb."""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(46, 28)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        self.update()
        if not self.signalsBlocked():
            self.toggled.emit(checked)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        track_h = 14
        track_y = (height - track_h) / 2.0
        track_radius = track_h / 2.0
        thumb_d = 20.0
        margin = 2.0

        if not self.isEnabled():
            track = QColor("#e0e0e0")
            thumb = QColor("#f5f5f5")
        elif self._checked:
            track = QColor(_ACCENT)
            thumb = QColor("#ffffff")
        else:
            track = QColor("#bdbdbd")
            thumb = QColor("#fafafa")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(track))
        painter.drawRoundedRect(
            QRectF(0, track_y, width, track_h), track_radius, track_radius
        )

        thumb_x = width - thumb_d - margin if self._checked else margin
        thumb_y = (height - thumb_d) / 2.0
        painter.setBrush(QBrush(thumb))
        painter.drawEllipse(QRectF(thumb_x, thumb_y, thumb_d, thumb_d))

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PreferenceRow(QFrame):
    activated = pyqtSignal()
    toggled = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        summary: str = "",
        *,
        icon: Optional[QIcon] = None,
        checkable: bool = False,
        navigable: bool = False,
        enabled: bool = True,
        unavailable: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._checkable = checkable
        self._navigable = navigable and not checkable
        self.setObjectName("preferenceRow")
        self.setStyleSheet(
            "QFrame#preferenceRow { background: #ffffff; "
            "border: none; border-bottom: 1px solid #e0e0e0; }"
            "QFrame#preferenceRow[hover='true'] { background: #f5f5f5; }"
            "QLabel { border: none; background: transparent; }"
        )
        self.setAttribute(Qt.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(16)

        if icon is not None and not icon.isNull():
            icon_label = QLabel()
            icon_label.setFixedSize(32, 32)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(icon.pixmap(24, 24))
            layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 15px; color: #212121;")
        text_layout.addWidget(self.title_label)

        self.summary_label = QLabel(summary)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #757575;")
        self.summary_label.setVisible(bool(summary))
        text_layout.addWidget(self.summary_label)
        layout.addLayout(text_layout, 1)

        self.switch: Optional[AndroidSwitch] = None
        if checkable:
            self.switch = AndroidSwitch()
            self.switch.toggled.connect(self.toggled.emit)
            layout.addWidget(self.switch, 0, Qt.AlignVCenter)

        self._apply_enabled(enabled, unavailable=unavailable and not enabled)
        self._update_cursor()

    def _apply_enabled(self, enabled: bool, *, unavailable: bool = False) -> None:
        self.setEnabled(enabled)
        if enabled:
            self.title_label.setStyleSheet("font-size: 15px; color: #212121;")
            self.summary_label.setStyleSheet("font-size: 13px; color: #757575;")
            self.setToolTip("")
            if self.switch is not None:
                self.switch.setEnabled(True)
        else:
            self.title_label.setStyleSheet("font-size: 15px; color: #bdbdbd;")
            self.summary_label.setStyleSheet("font-size: 13px; color: #c7c7c7;")
            self.setToolTip(_UNAVAILABLE if unavailable else "")
            if self.switch is not None:
                self.switch.setEnabled(False)
        self._update_cursor()

    def set_interactive(self, interactive: bool, *, unavailable: bool = False) -> None:
        self._navigable = interactive and self.switch is None
        self._apply_enabled(interactive, unavailable=unavailable)

    def _update_cursor(self) -> None:
        if self.isEnabled() and (self._checkable or self._navigable):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def set_summary(self, summary: str) -> None:
        self.summary_label.setText(summary)
        self.summary_label.setVisible(bool(summary))

    def set_checked(self, checked: bool) -> None:
        if self.switch is None:
            return
        blocked = self.switch.blockSignals(True)
        self.switch.setChecked(checked)
        self.switch.blockSignals(blocked)

    def enterEvent(self, event) -> None:
        if self.isEnabled():
            self.setProperty("hover", True)
            self.style().unpolish(self)
            self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.LeftButton:
            if self.switch is not None:
                self.switch.setChecked(not self.switch.isChecked())
            elif self._navigable:
                self.activated.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PreferenceScreen(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #ffffff;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if title:
            header = QWidget()
            header.setFixedHeight(56)
            header.setStyleSheet(
                "background: #fafafa; border-bottom: 1px solid #e0e0e0;"
            )
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(4, 0, 16, 0)
            header_layout.setSpacing(4)

            back = QToolButton()
            back.setText("←")
            back.setToolTip("返回")
            back.setFixedSize(48, 48)
            back.setStyleSheet(
                "QToolButton { border: none; background: transparent; "
                "font-size: 22px; color: #424242; }"
                "QToolButton:hover { background: #eeeeee; border-radius: 24px; }"
            )
            back.clicked.connect(self.back_requested.emit)
            header_layout.addWidget(back)

            label = QLabel(title)
            label.setStyleSheet("font-size: 18px; font-weight: 600; color: #212121;")
            header_layout.addWidget(label, 1)
            root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: #ffffff; border: none; }")
        root.addWidget(scroll, 1)

        content = QWidget()
        content.setStyleSheet("background: #ffffff;")
        scroll.setWidget(content)
        self.rows = QVBoxLayout(content)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.rows.addStretch(1)

    def add_row(self, row: PreferenceRow) -> PreferenceRow:
        self.rows.insertWidget(self.rows.count() - 1, row)
        return row


class SettingsPage(QWidget):
    settings_saved = pyqtSignal()

    def __init__(
        self,
        robot: RobotInfo,
        robot_store: RobotStore,
        session: Optional[RobotSession] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._robot_store = robot_store
        self._session = session
        self._loading = False
        self._stack = QStackedWidget()
        self._rows: Dict[str, PreferenceRow] = {}
        self._build_ui()
        self._reload_rows()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._stack)

        self._root_screen = self._build_root_screen()
        self._topic_screen = self._build_topic_screen()
        self._slam_screen = self._build_slam_screen()
        self._warning_screen = self._build_warning_screen()
        self._advanced_screen = self._build_advanced_screen()
        for screen in (
            self._root_screen,
            self._topic_screen,
            self._slam_screen,
            self._warning_screen,
            self._advanced_screen,
        ):
            self._stack.addWidget(screen)
        self._stack.setCurrentWidget(self._root_screen)

    def _build_root_screen(self) -> PreferenceScreen:
        screen = PreferenceScreen()
        topics = screen.add_row(
            PreferenceRow(
                S.TOPIC_PREF_TITLE,
                S.TOPIC_PREF_SUMMARY,
                icon=_android_icon("ic_action_topics.png"),
                navigable=True,
            )
        )
        topics.activated.connect(lambda: self._show_screen(self._topic_screen))

        warning = screen.add_row(
            PreferenceRow(
                S.WARNING_PREF_TITLE,
                S.WARNING_PREF_SUMMARY,
                icon=_android_icon("ic_warning_system.png"),
                navigable=True,
            )
        )
        warning.activated.connect(lambda: self._show_screen(self._warning_screen))

        advanced = screen.add_row(
            PreferenceRow(
                S.ADVANCED_CONTROLS_PREF_TITLE,
                S.PREFS_ADVANCED_CONTROL_SETTINGS_SUMMARY,
                icon=_android_icon("ic_settings_ethernet_black_24dp.png"),
                navigable=True,
            )
        )
        advanced.activated.connect(lambda: self._show_screen(self._advanced_screen))
        return screen

    def _build_topic_screen(self) -> PreferenceScreen:
        screen = PreferenceScreen(S.TOPIC_PREF_TITLE)
        screen.back_requested.connect(self._show_root)
        for key in S.TOPIC_TITLE_BY_KEY:
            title = S.TOPIC_TITLE_BY_KEY[key]
            row = screen.add_row(PreferenceRow(title, navigable=True))
            row.activated.connect(
                lambda key=key, title=title: self._edit_topic(key, title)
            )
            self._rows[key] = row

        slam = screen.add_row(
            PreferenceRow(
                S.SLAM_BOUNDS_PREF_TITLE,
                S.SLAM_BOUNDS_PREF_SUMMARY,
                navigable=True,
            )
        )
        slam.activated.connect(lambda: self._show_screen(self._slam_screen))
        return screen

    def _build_slam_screen(self) -> PreferenceScreen:
        screen = PreferenceScreen(S.SLAM_BOUNDS_PREF_TITLE)
        screen.back_requested.connect(lambda: self._show_screen(self._topic_screen))
        for key, title in (
            ("slam_xmin", S.SLAM_XMIN_PREF_TITLE),
            ("slam_xmax", S.SLAM_XMAX_PREF_TITLE),
            ("slam_ymin", S.SLAM_YMIN_PREF_TITLE),
            ("slam_ymax", S.SLAM_YMAX_PREF_TITLE),
        ):
            row = screen.add_row(PreferenceRow(title, navigable=True))
            row.activated.connect(lambda key=key, title=title: self._edit_float(key, title))
            self._rows[key] = row
        return screen

    def _build_warning_screen(self) -> PreferenceScreen:
        screen = PreferenceScreen(S.WARNING_PREF_TITLE)
        screen.back_requested.connect(self._show_root)

        enabled = screen.add_row(
            PreferenceRow(
                S.WARNING_ENABLE_PREF_TITLE,
                S.WARNING_ENABLE_PREF_SUMMARY_OFF,
                checkable=True,
            )
        )
        enabled.toggled.connect(self._on_warning_enabled_toggled)
        safe = screen.add_row(
            PreferenceRow(
                S.WARNING_SAFEMODE_PREF_TITLE,
                S.WARNING_SAFEMODE_PREF_SUMMARY_OFF,
                checkable=True,
            )
        )
        safe.toggled.connect(
            lambda checked: self._toggle_value("warning_safemode", checked)
        )
        beep = screen.add_row(
            PreferenceRow(
                S.WARNING_BEEP_PREF_TITLE,
                S.WARNING_BEEP_PREF_SUMMARY_OFF,
                checkable=True,
            )
        )
        beep.toggled.connect(
            lambda checked: self._toggle_value("warning_beep", checked)
        )
        distance = screen.add_row(
            PreferenceRow(S.WARNING_MINDIST_PREF_TITLE, navigable=True)
        )
        distance.activated.connect(
            lambda: self._edit_float(
                "warning_min_distance",
                S.WARNING_MINDIST_PREF_TITLE,
                0.2,
                20.0,
            )
        )
        self._rows.update(
            {
                "warning_enabled": enabled,
                "warning_safemode": safe,
                "warning_beep": beep,
                "warning_min_distance": distance,
            }
        )
        return screen

    def _build_advanced_screen(self) -> PreferenceScreen:
        screen = PreferenceScreen(S.ADVANCED_CONTROLS_PREF_TITLE)
        screen.back_requested.connect(self._show_root)

        detail = screen.add_row(
            PreferenceRow(
                S.LASER_SCAN_DETAIL_PREF_TITLE,
                enabled=False,
                unavailable=True,
            )
        )
        proximity = screen.add_row(
            PreferenceRow(
                S.RANDOM_WALK_RANGE_MINIMUM_PREF_TITLE,
                enabled=False,
                unavailable=True,
            )
        )
        reverse = screen.add_row(
            PreferenceRow(
                S.REVERSE_ANGLE_READING_TITLE,
                S.REVERSE_ANGLE_READING_SUMMARY_OFF,
                checkable=True,
                enabled=False,
                unavailable=True,
            )
        )
        self._rows["laser_scan_detail"] = detail
        self._rows["random_walk_range_proximity"] = proximity
        self._rows["reverse_laser_scan"] = reverse

        for key, title, summary in (
            ("invert_x", S.INVERT_X_AXIS_TITLE, S.INVERT_X_AXIS_SUMMARY),
            ("invert_y", S.INVERT_Y_AXIS_TITLE, S.INVERT_Y_AXIS_SUMMARY),
            (
                "invert_angular_velocity",
                S.INVERT_ANGULAR_VELOCITY_TITLE,
                S.INVERT_ANGULAR_VELOCITY_SUMMARY,
            ),
        ):
            row = screen.add_row(
                PreferenceRow(title, summary, checkable=True)
            )
            row.toggled.connect(lambda checked, key=key: self._toggle_value(key, checked))
            self._rows[key] = row

        linear = screen.add_row(
            PreferenceRow(S.MANUAL_LINEAR_SPEED_PREF_TITLE, navigable=True)
        )
        linear.activated.connect(
            lambda: self._edit_float(
                "manual_linear_speed",
                S.MANUAL_LINEAR_SPEED_PREF_TITLE,
                MANUAL_LINEAR_MIN,
                MANUAL_LINEAR_MAX,
            )
        )
        angular = screen.add_row(
            PreferenceRow(S.MANUAL_ANGULAR_SPEED_PREF_TITLE, navigable=True)
        )
        angular.activated.connect(
            lambda: self._edit_float(
                "manual_angular_speed",
                S.MANUAL_ANGULAR_SPEED_PREF_TITLE,
                MANUAL_ANGULAR_MIN,
                MANUAL_ANGULAR_MAX,
            )
        )
        self._rows["manual_linear_speed"] = linear
        self._rows["manual_angular_speed"] = angular
        return screen

    def _show_screen(self, screen: PreferenceScreen) -> None:
        self._stack.setCurrentWidget(screen)

    def _show_root(self) -> None:
        self._show_screen(self._root_screen)

    def on_page_activated(self) -> None:
        self._reload_rows()

    def on_page_deactivated(self) -> None:
        self._show_root()

    def _reload_rows(self) -> None:
        self._loading = True
        robot = self._robot
        for key, template in S.TOPIC_SUMMARY_BY_KEY.items():
            self._rows[key].set_summary(template % getattr(robot, key))

        for key in ("slam_xmin", "slam_xmax", "slam_ymin", "slam_ymax"):
            self._rows[key].set_summary(
                S.SLAM_BOUND_PREF_SUMMARY % f"{getattr(robot, key):g}"
            )

        self._rows["warning_enabled"].set_checked(robot.warning_enabled)
        self._rows["warning_enabled"].set_summary(
            S.WARNING_ENABLE_PREF_SUMMARY_ON
            if robot.warning_enabled
            else S.WARNING_ENABLE_PREF_SUMMARY_OFF
        )
        self._rows["warning_safemode"].set_checked(robot.warning_safemode)
        self._rows["warning_safemode"].set_summary(
            S.WARNING_SAFEMODE_PREF_SUMMARY_ON
            if robot.warning_safemode
            else S.WARNING_SAFEMODE_PREF_SUMMARY_OFF
        )
        self._rows["warning_beep"].set_checked(robot.warning_beep)
        self._rows["warning_beep"].set_summary(
            S.WARNING_BEEP_PREF_SUMMARY_ON
            if robot.warning_beep
            else S.WARNING_BEEP_PREF_SUMMARY_OFF
        )
        self._rows["warning_min_distance"].set_summary(
            S.WARNING_MINDIST_PREF_SUMMARY % f"{robot.warning_min_distance:g}"
        )

        self._rows["laser_scan_detail"].set_summary(
            S.LASER_SCAN_DETAIL_PREF_SUMMARY % str(robot.laser_scan_detail)
        )
        self._rows["random_walk_range_proximity"].set_summary(
            S.RANDOM_WALK_RANGE_MINIMUM_PREF_SUMMARY
            % f"{robot.random_walk_range_proximity:g}"
        )
        self._rows["reverse_laser_scan"].set_checked(robot.reverse_laser_scan)
        self._rows["reverse_laser_scan"].set_summary(
            S.REVERSE_ANGLE_READING_SUMMARY_ON
            if robot.reverse_laser_scan
            else S.REVERSE_ANGLE_READING_SUMMARY_OFF
        )
        self._rows["invert_x"].set_checked(robot.invert_x)
        self._rows["invert_y"].set_checked(robot.invert_y)
        self._rows["invert_angular_velocity"].set_checked(
            robot.invert_angular_velocity
        )

        linear = robot.manual_linear_speed
        if linear is None:
            linear = DEFAULT_MANUAL_LINEAR
        angular = robot.manual_angular_speed
        if angular is None:
            angular = DEFAULT_MANUAL_ANGULAR
        self._rows["manual_linear_speed"].set_summary(
            S.MANUAL_LINEAR_SPEED_PREF_SUMMARY % f"{linear:g}"
        )
        self._rows["manual_angular_speed"].set_summary(
            S.MANUAL_ANGULAR_SPEED_PREF_SUMMARY % f"{angular:g}"
        )
        self._sync_warning_dependencies()
        self._loading = False

    def _sync_warning_dependencies(self) -> None:
        active = self._robot.warning_enabled
        for key in ("warning_safemode", "warning_beep", "warning_min_distance"):
            self._rows[key].set_interactive(active, unavailable=False)

    def _on_warning_enabled_toggled(self, checked: bool) -> None:
        if not self._loading:
            self._commit({"warning_enabled": checked})
        self._sync_warning_dependencies()

    def _prompt_value(
        self,
        title: str,
        current: str,
        *,
        integer: bool = False,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> Optional[str]:
        dialog, edit = build_value_dialog(
            self,
            title,
            current,
            integer=integer,
            minimum=minimum,
            maximum=maximum,
        )
        edit.setFocus()
        if exec_value_dialog(self.window(), dialog) != QDialog.Accepted:
            return None
        value = edit.text().strip()
        if not value:
            QMessageBox.warning(self, title, "值不能为空。")
            return None
        return value

    def _edit_topic(self, key: str, title: str) -> None:
        value = self._prompt_value(title, str(getattr(self._robot, key)))
        if value is not None:
            self._commit({key: value})

    def _edit_float(
        self,
        key: str,
        title: str,
        minimum: float = -100.0,
        maximum: float = 100.0,
    ) -> None:
        current = getattr(self._robot, key)
        if current is None:
            current = 0.0
        value = self._prompt_value(
            title,
            f"{float(current):g}",
            minimum=minimum,
            maximum=maximum,
        )
        if value is not None:
            self._commit({key: float(value)})

    def _toggle_value(self, key: str, checked: bool) -> None:
        if not self._loading:
            self._commit({key: checked})

    def _commit(self, values: Dict[str, object]) -> bool:
        candidate = replace(self._robot, **values)
        if candidate.slam_xmin >= candidate.slam_xmax:
            QMessageBox.warning(
                self, S.SLAM_BOUNDS_PREF_TITLE, "SLAM X 最小值须小于最大值。"
            )
            self._reload_rows()
            return False
        if candidate.slam_ymin >= candidate.slam_ymax:
            QMessageBox.warning(
                self, S.SLAM_BOUNDS_PREF_TITLE, "SLAM Y 最小值须小于最大值。"
            )
            self._reload_rows()
            return False
        if not self._robot_store.update(candidate):
            QMessageBox.warning(
                self,
                S.ADVANCED_CONTROLS_PREF_TITLE,
                "保存失败：无法写入 robots.json 或当前机器人记录不存在。",
            )
            self._reload_rows()
            return False

        for field in fields(RobotInfo):
            setattr(self._robot, field.name, getattr(candidate, field.name))
        self._reload_rows()
        self.settings_saved.emit()
        return True

    # Used by off-screen screenshot harness.
    def show_topic_screen(self) -> None:
        self._show_screen(self._topic_screen)

    def show_warning_screen(self) -> None:
        self._show_screen(self._warning_screen)

    def show_advanced_screen(self) -> None:
        self._show_screen(self._advanced_screen)
