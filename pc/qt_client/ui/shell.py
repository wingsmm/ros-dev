from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.assets import android_asset


@dataclass(frozen=True)
class PageDef:
    page_id: str
    title: str
    icon: str = ""


PAGES: List[PageDef] = [
    PageDef("robot_list", "选择机器人", "[R]"),
    PageDef("help", "帮助", "[?]"),
    PageDef("about", "关于", "[i]"),
]


class TopBar(QWidget):
    menu_clicked = pyqtSignal()
    back_clicked = pyqtSignal()
    add_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nav_mode = "menu"
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedHeight(64)
        self.setStyleSheet("background: #f7f7f7; border-bottom: 1px solid #ddd;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.nav_btn = QPushButton()
        self.nav_btn.setFixedSize(44, 44)
        self.nav_btn.setIconSize(QSize(24, 24))
        self.nav_btn.clicked.connect(self._on_nav_clicked)
        layout.addWidget(self.nav_btn)

        self.title_label = QLabel("选择机器人")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.title_label, 1)

        self.add_btn = QPushButton()
        self.add_btn.setFixedSize(44, 44)
        self.add_btn.setIconSize(QSize(28, 28))
        self.add_btn.setIcon(QIcon(android_asset("ic_add_circle_black_24dp.png")))
        self.add_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: #ececec; border-radius: 6px; }"
        )
        self.add_btn.clicked.connect(self.add_clicked.emit)
        layout.addWidget(self.add_btn)

        self.set_nav_mode("menu")
        self.set_add_visible(True)

    def _on_nav_clicked(self) -> None:
        if self._nav_mode == "back":
            self.back_clicked.emit()
        else:
            self.menu_clicked.emit()

    def set_nav_mode(self, mode: str) -> None:
        self._nav_mode = mode
        if mode == "back":
            self.nav_btn.setText("←")
            self.nav_btn.setIcon(QIcon())
            self.nav_btn.setToolTip("返回")
        else:
            self.nav_btn.setText("☰")
            self.nav_btn.setIcon(QIcon())
            self.nav_btn.setToolTip("菜单")

    def set_add_visible(self, visible: bool) -> None:
        self.add_btn.setVisible(visible)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class Drawer(QWidget):
    page_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: Dict[str, QPushButton] = {}
        self._active_id = "robot_list"
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedWidth(320)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "Drawer { background-color: #ffffff; border-right: 1px solid #ddd; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        for p in PAGES:
            btn = QPushButton(f"{p.icon}  {p.title}".strip())
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(64)
            btn.setStyleSheet(
                "QPushButton{ text-align:left; padding-left: 22px; border:none; font-size: 15px; }"
                "QPushButton:hover{ background:#f3f3f3; }"
            )
            btn.clicked.connect(lambda _=False, pid=p.page_id: self.page_selected.emit(pid))
            root.addWidget(btn)
            self._buttons[p.page_id] = btn

        root.addStretch(1)
        self.set_active("robot_list")

    def set_active(self, page_id: str) -> None:
        self._active_id = page_id
        for pid, btn in self._buttons.items():
            if pid == page_id:
                btn.setStyleSheet(
                    "QPushButton{ text-align:left; padding-left: 22px; border:none; background:#efefef; font-size: 15px; }"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{ text-align:left; padding-left: 22px; border:none; font-size: 15px; }"
                    "QPushButton:hover{ background:#f3f3f3; }"
                )


class Overlay(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(0,0,0,0.45);")
        self.hide()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        event.accept()


class AppShell(QWidget):
    """
    Android 风格页面壳：TopBar + Drawer + PageStack（QStackedWidget）
    支持 push_page / pop_page 子页面返回栈。
    """

    log = pyqtSignal(str)
    page_popped = pyqtSignal(str)

    def __init__(self, pages: Dict[str, QWidget], parent=None):
        super().__init__(parent)
        self._page_widgets = dict(pages)
        self._stack = QStackedWidget()
        self._drawer_open = False
        self._drawer_width = 320
        self._drawer_anim: QPropertyAnimation | None = None
        self._page_titles: Dict[str, str] = {p.page_id: p.title for p in PAGES}
        self._current_base_id = "robot_list"
        self._push_stack: List[Tuple[str, str, QWidget]] = []
        self._build_ui()
        self.set_page("robot_list")

    def _current_push_widget(self) -> QWidget | None:
        if not self._push_stack:
            return None
        return self._push_stack[-1][2]

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.topbar = TopBar()
        self.topbar.menu_clicked.connect(self.toggle_drawer)
        self.topbar.back_clicked.connect(self.pop_page)
        root.addWidget(self.topbar)

        for widget in self._page_widgets.values():
            self._stack.addWidget(widget)
        root.addWidget(self._stack, 1)

        self.overlay = Overlay(self)
        self.overlay.clicked.connect(self.close_drawer)
        self.drawer = Drawer(self)
        self.drawer.page_selected.connect(self._on_drawer_select)
        self.drawer.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_layer_geometry()

    def _content_rect(self) -> QRect:
        body_top = self.topbar.height()
        body_height = max(0, self.height() - body_top)
        return QRect(0, body_top, self.width(), body_height)

    def _overlay_rect(self) -> QRect:
        content_rect = self._content_rect()
        return QRect(
            self._drawer_width,
            content_rect.y(),
            max(0, content_rect.width() - self._drawer_width),
            content_rect.height(),
        )

    def _drawer_rect(self, opened: bool) -> QRect:
        content_rect = self._content_rect()
        x = 0 if opened else -self._drawer_width
        return QRect(x, content_rect.y(), self._drawer_width, content_rect.height())

    def _sync_layer_geometry(self) -> None:
        self.overlay.setGeometry(self._overlay_rect())
        self.drawer.setGeometry(self._drawer_rect(opened=self._drawer_open))

    def _sync_overlay_geometry(self) -> None:
        self.overlay.setGeometry(self._overlay_rect())

    def _animate_drawer(self, opened: bool) -> None:
        if self._drawer_anim is not None:
            self._drawer_anim.stop()

        self.drawer.show()
        self.drawer.raise_()
        self._drawer_anim = QPropertyAnimation(self.drawer, b"geometry", self)
        self._drawer_anim.setDuration(180)
        self._drawer_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._drawer_anim.setStartValue(self.drawer.geometry())
        self._drawer_anim.setEndValue(self._drawer_rect(opened))
        if not opened:
            self._drawer_anim.finished.connect(self._after_drawer_closed)
        self._drawer_anim.start()

    def _after_drawer_closed(self) -> None:
        if self._drawer_open:
            return
        self.drawer.hide()
        self.overlay.hide()

    def toggle_drawer(self) -> None:
        pushed_widget = self._current_push_widget()
        if pushed_widget is not None and hasattr(pushed_widget, "toggle_navigation"):
            pushed_widget.toggle_navigation()
            return
        if self._drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self) -> None:
        if self._drawer_open:
            return
        self.drawer.setGeometry(self._drawer_rect(opened=False))
        self._drawer_open = True
        self._sync_overlay_geometry()
        self.overlay.show()
        self.overlay.raise_()
        self._animate_drawer(opened=True)

    def close_drawer(self) -> None:
        if not self._drawer_open:
            return
        self._drawer_open = False
        self._animate_drawer(opened=False)

    def _on_drawer_select(self, page_id: str) -> None:
        self.set_page(page_id)
        self.close_drawer()

    def _clear_push_stack(self) -> None:
        self._push_stack.clear()

    def _update_topbar_for_base(self, page_id: str) -> None:
        self.topbar.set_nav_mode("menu")
        self.topbar.set_title(self._page_titles.get(page_id, page_id))
        self.topbar.set_add_visible(page_id == "robot_list")

    def set_page(self, page_id: str) -> None:
        widget = self._page_widgets.get(page_id)
        if widget is None:
            return
        self._clear_push_stack()
        self._current_base_id = page_id
        self._stack.setCurrentWidget(widget)
        self.drawer.set_active(page_id)
        self._update_topbar_for_base(page_id)
        self.log.emit(f"Shell page -> {page_id}")

    def push_page(self, page_id: str, title: str, widget: QWidget) -> None:
        if self._stack.indexOf(widget) < 0:
            self._stack.addWidget(widget)
        self._push_stack.append((page_id, title, widget))
        self._stack.setCurrentWidget(widget)
        self.topbar.set_nav_mode("menu")
        self.topbar.set_add_visible(False)
        self.topbar.set_title(title)
        self.log.emit(f"Shell push -> {page_id}: {title}")

    def pop_page(self) -> None:
        if not self._push_stack:
            return
        popped = self._push_stack.pop()
        page_id = popped[0]
        self.log.emit(f"Shell pop <- {page_id}")
        if self._push_stack:
            _, title, widget = self._push_stack[-1]
            self._stack.setCurrentWidget(widget)
            self.topbar.set_nav_mode("menu")
            self.topbar.set_add_visible(False)
            self.topbar.set_title(title)
            self.page_popped.emit(page_id)
            return
        widget = self._page_widgets.get(self._current_base_id)
        if widget is not None:
            self._stack.setCurrentWidget(widget)
        self._update_topbar_for_base(self._current_base_id)
        self.page_popped.emit(page_id)

    def is_on_base_page(self) -> bool:
        return not self._push_stack
