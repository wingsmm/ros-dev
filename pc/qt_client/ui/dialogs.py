from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QWidget


def make_modal_dialog(parent, title: str, width: int = 720) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setModal(True)
    if width > 0:
        dialog.setMinimumWidth(width)
    dialog.setStyleSheet("QDialog { background: #ffffff; }")
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return dialog


def resize_and_center_dialog(parent, dialog: QDialog) -> None:
    dialog.adjustSize()
    parent_geo = parent.frameGeometry()
    dialog_geo = dialog.frameGeometry()
    dialog.move(parent_geo.center() - dialog_geo.center())


def exec_modal_dialog(parent, dialog: QDialog, shell: QWidget | None = None) -> int:
    scrim = None
    if shell is not None:
        scrim = QWidget(shell)
        scrim.setGeometry(shell.rect())
        scrim.setStyleSheet("background: rgba(0, 0, 0, 0.55);")
        scrim.show()
        scrim.raise_()
    resize_and_center_dialog(parent, dialog)
    try:
        return dialog.exec_()
    finally:
        if scrim is not None:
            scrim.hide()
            scrim.deleteLater()
