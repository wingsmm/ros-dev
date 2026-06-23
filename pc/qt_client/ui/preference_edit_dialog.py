from __future__ import annotations

from typing import Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui import android_prefs_strings as S
from ui.dialogs import resize_and_center_dialog

_ACCENT = "#009688"
_DIALOG_BUTTON_STYLE = (
    f"QPushButton {{ color: {_ACCENT}; border: none; padding: 10px 16px; "
    "font-size: 14px; }}"
    "QPushButton:hover { background: #eeeeee; }"
)


def build_value_dialog(
    parent: QWidget,
    title: str,
    current: str,
    *,
    integer: bool = False,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Tuple[QDialog, QLineEdit]:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    dialog.setMinimumWidth(480)
    dialog.setStyleSheet(
        "QDialog { background: #ffffff; }"
        f"QLineEdit {{ border: none; border-bottom: 2px solid {_ACCENT}; "
        "padding: 10px 2px; font-size: 18px; color: #212121; }}"
        f"{_DIALOG_BUTTON_STYLE}"
    )
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 16, 12)
    layout.setSpacing(20)

    heading = QLabel(title)
    heading.setStyleSheet("font-size: 20px; color: #212121;")
    layout.addWidget(heading)

    edit = QLineEdit(current)
    edit.selectAll()
    if integer:
        validator = QIntValidator(edit)
        if minimum is not None:
            validator.setBottom(int(minimum))
        if maximum is not None:
            validator.setTop(int(maximum))
        edit.setValidator(validator)
    elif minimum is not None or maximum is not None:
        validator = QDoubleValidator(edit)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setDecimals(3)
        validator.setBottom(minimum if minimum is not None else -1000000.0)
        validator.setTop(maximum if maximum is not None else 1000000.0)
        edit.setValidator(validator)
    layout.addWidget(edit)

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch(1)
    cancel_btn = QPushButton(S.CANCEL)
    ok_btn = QPushButton(S.OK)
    cancel_btn.setStyleSheet(_DIALOG_BUTTON_STYLE)
    ok_btn.setStyleSheet(_DIALOG_BUTTON_STYLE)
    cancel_btn.clicked.connect(dialog.reject)
    ok_btn.clicked.connect(dialog.accept)
    row.addWidget(cancel_btn)
    row.addWidget(ok_btn)
    layout.addLayout(row)

    return dialog, edit


def exec_value_dialog(parent_window: QWidget, dialog: QDialog) -> int:
    resize_and_center_dialog(parent_window, dialog)
    return dialog.exec_()
