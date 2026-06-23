from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMainWindow, QProgressDialog

from backends import create_backend
from core import RobotSession
from ui.dialogs import exec_modal_dialog, make_modal_dialog
from ui.models import RobotStore
from ui.pages import RobotDeletePage, RobotFormPage, RobotListPage, RobotWorkspacePage
from ui.shell import AppShell


class RobotShellController:
    def __init__(
        self,
        window: QMainWindow,
        shell: AppShell,
        robot_store: RobotStore,
        robot_list_page: RobotListPage,
        log_fn: Callable[[str], None],
    ) -> None:
        self._window = window
        self._shell = shell
        self._robot_store = robot_store
        self._robot_list_page = robot_list_page
        self._log = log_fn
        self._session: Optional[RobotSession] = None
        self._workspace: Optional[RobotWorkspacePage] = None

        shell.topbar.add_clicked.connect(self._open_add_robot_dialog)
        shell.page_popped.connect(self._on_page_popped)
        robot_list_page.robot_selected.connect(self._on_robot_selected)
        robot_list_page.robot_edit_requested.connect(self._open_edit_robot_dialog)
        robot_list_page.robot_delete_requested.connect(self._open_delete_robot_dialog)

    def refresh_robot_list(self) -> None:
        self._robot_list_page.set_robots(self._robot_store.robots())

    def cleanup(self) -> None:
        if self._workspace is not None:
            self._workspace.shutdown()
            self._workspace = None
        if self._session is not None:
            self._session.cleanup()
            self._session = None

    def _open_add_robot_dialog(self) -> None:
        form = RobotFormPage()
        form.prepare_add()
        self._show_robot_form_dialog(form, "添加/编辑机器人")

    def _open_edit_robot_dialog(self, robot_id: str) -> None:
        robot = self._robot_store.get(robot_id)
        if robot is None:
            return
        form = RobotFormPage()
        form.prepare_edit(robot)
        self._show_robot_form_dialog(form, "添加/编辑机器人")

    def _open_delete_robot_dialog(self, robot_id: str) -> None:
        robot = self._robot_store.get(robot_id)
        if robot is None:
            return
        page = RobotDeletePage()
        page.prepare(robot)

        dialog = make_modal_dialog(self._window, "删除", width=520)
        dialog.layout().addWidget(page)
        page.cancel_requested.connect(dialog.reject)
        page.delete_confirmed.connect(
            lambda rid: self._delete_robot_from_dialog(rid, dialog)
        )
        exec_modal_dialog(self._window, dialog, shell=self._shell)

    def _show_robot_form_dialog(self, form: RobotFormPage, title: str) -> None:
        dialog = make_modal_dialog(self._window, title, width=0)
        dialog.layout().addWidget(form)
        form.cancel_requested.connect(dialog.reject)
        form.save_requested.connect(
            lambda robot: self._save_robot_from_dialog(robot, dialog)
        )
        exec_modal_dialog(self._window, dialog, shell=self._shell)

    def _save_robot_from_dialog(self, robot, dialog) -> None:
        if self._on_robot_form_saved(robot):
            dialog.accept()

    def _delete_robot_from_dialog(self, robot_id: str, dialog) -> None:
        if self._on_robot_delete_confirmed(robot_id):
            dialog.accept()

    def _on_robot_selected(self, robot_id: str) -> None:
        robot = self._robot_store.get(robot_id)
        if robot is None:
            return

        if self._session is not None:
            self._session.cleanup()
            self._session = None

        backend = create_backend(robot)
        session = RobotSession(robot, backend)
        self._session = session

        progress = QProgressDialog(
            f"正在连接 {robot.name}（{robot.master_uri}）",
            "",
            0,
            0,
            self._window,
        )
        progress.setWindowTitle("正在连接")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(True)
        progress.show()

        def finish_connect() -> None:
            ok = session.connect()
            progress.close()
            if ok:
                self._log(
                    f"Robot connected ({robot.backend_type}): "
                    f"{robot.name} ({robot.master_uri})"
                )
                self._open_robot_workspace(robot, session)
            else:
                self._session = None
                session.cleanup()
                self._log(
                    f"Robot connect failed: {robot.name} - {session.last_error}"
                )

        QTimer.singleShot(900, finish_connect)

    def _open_robot_workspace(self, robot, session: RobotSession) -> None:
        workspace = RobotWorkspacePage(
            robot, session=session, robot_store=self._robot_store
        )
        self._workspace = workspace
        workspace.back_requested.connect(self._shell.pop_page)
        self._shell.push_page(
            page_id=f"robot_workspace:{robot.id}",
            title=robot.name,
            widget=workspace,
        )

    def _on_page_popped(self, page_id: str) -> None:
        if not page_id.startswith("robot_workspace:"):
            return
        if self._workspace is not None:
            self._workspace.shutdown()
            self._workspace = None
        if self._session is not None:
            self._session.cleanup()
            self._session = None

    def _on_robot_form_saved(self, robot) -> bool:
        if self._robot_store.get(robot.id):
            saved = self._robot_store.update(robot)
            action = "updated"
        else:
            saved = self._robot_store.add(robot)
            action = "added"
        if not saved:
            self._log(f"Robot save failed: {robot.name}")
            return False
        self._log(f"Robot {action}: {robot.name}")
        self.refresh_robot_list()
        return True

    def _on_robot_delete_confirmed(self, robot_id: str) -> bool:
        robot = self._robot_store.get(robot_id)
        if robot is None:
            return False
        if not self._robot_store.remove(robot_id):
            self._log(f"Robot delete failed: {robot.name}")
            return False
        self._log(f"Robot deleted: {robot.name}")
        self.refresh_robot_list()
        return True
