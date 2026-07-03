from PyQt5.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TopicPanel(QWidget):
    def __init__(self, parent=None):
        super(TopicPanel, self).__init__(parent)
        self.summary = QLabel("尚未检查 topic")
        self.summary.setWordWrap(True)

        self.btn_probe = QPushButton("检查关键 topic")
        self.btn_depth = QPushButton("深度诊断 (/camera/depth/image_raw)")

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(140)

        box = QGroupBox("Topic 诊断")
        layout = QVBoxLayout(box)
        layout.addWidget(self.summary)
        layout.addWidget(self.btn_probe)
        layout.addWidget(self.btn_depth)
        layout.addWidget(self.detail)

        outer = QVBoxLayout(self)
        outer.addWidget(box)

    def set_summary(self, text):
        self.summary.setText(text)

    def set_detail(self, text):
        self.detail.setPlainText(text)

    def append_detail(self, text):
        self.detail.append(text)
