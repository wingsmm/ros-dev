from __future__ import annotations

from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    MAX_LOG_LINES = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        group = QGroupBox("JSON 日志")
        group_layout = QVBoxLayout(group)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.document().setMaximumBlockCount(self.MAX_LOG_LINES)
        group_layout.addWidget(self.text)

        btn_row = QHBoxLayout()
        self.clear_btn = QPushButton("清空")
        btn_row.addStretch(1)
        btn_row.addWidget(self.clear_btn)
        group_layout.addLayout(btn_row)

        layout.addWidget(group)
        self.clear_btn.clicked.connect(self.text.clear)

    def append(self, line: str) -> None:
        self.text.appendPlainText(line)
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.maximum())
