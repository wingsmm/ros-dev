from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    MAX_LOG_LINES = 2000

    def __init__(self, parent=None):
        super(LogPanel, self).__init__(parent)
        group = QGroupBox("运行日志")
        layout = QVBoxLayout(group)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.document().setMaximumBlockCount(self.MAX_LOG_LINES)
        layout.addWidget(self.text)

        row = QHBoxLayout()
        self.clear_btn = QPushButton("清空")
        row.addStretch(1)
        row.addWidget(self.clear_btn)
        layout.addLayout(row)

        outer = QVBoxLayout(self)
        outer.addWidget(group)
        self.clear_btn.clicked.connect(self.text.clear)

    def append(self, line):
        self.text.appendPlainText(line)
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.maximum())
