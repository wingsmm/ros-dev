from __future__ import annotations

import logging
from datetime import datetime

from PyQt5.QtWidgets import QMainWindow

from core.app_shutdown import run_shutdown
from core.logging_config import log_ui_line
from ui.models import RobotStore
from ui.pages import PlaceholderPage, RobotListPage
from ui.robot_shell_controller import RobotShellController
from ui.shell import AppShell

APP_TITLE = "xtark Console"

logger = logging.getLogger(__name__)


class ShellMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(980, 820)
        self._cleanup_done = False

        self._robot_store = RobotStore()
        robot_list = RobotListPage()
        pages = {
            "robot_list": robot_list,
            "help": PlaceholderPage("帮助"),
            "about": PlaceholderPage("关于"),
        }
        shell = AppShell(pages=pages)
        shell.log.connect(self._on_log)
        self.shell = shell
        self._shell_controller = RobotShellController(
            window=self,
            shell=shell,
            robot_store=self._robot_store,
            robot_list_page=robot_list,
            log_fn=self._on_log,
        )
        self._shell_controller.refresh_robot_list()
        self.setCentralWidget(shell)

    def _on_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = "[{stamp}] {text}".format(stamp=stamp, text=text)
        log_ui_line(line)

    def cleanup(self) -> None:
        if self._cleanup_done:
            return
        self._cleanup_done = True
        logger.info("main window cleanup")
        self._shell_controller.cleanup()
        run_shutdown()

    def closeEvent(self, event) -> None:
        self.cleanup()
        super().closeEvent(event)


def create_main_window(enable_ros2: bool, legacy_ui: bool) -> QMainWindow:
    if legacy_ui:
        from legacy.legacy_window import LegacyWindow

        return LegacyWindow(enable_ros2=enable_ros2)
    return ShellMainWindow()
