from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QToolButton, QVBoxLayout, QWidget

from ui.widgets.robot_telemetry_panel import RobotTelemetryPanel


class TelemetryDetailsStrip(QWidget):
    """Collapsible chassis telemetry block; collapsed by default."""

    expanded_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._toggle = QToolButton()
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setAutoRaise(True)
        self._toggle.setStyleSheet(
            "QToolButton { color: #444; font-size: 13px; padding: 2px 4px; }"
            "QToolButton:hover { background: #eee; border-radius: 4px; }"
        )
        self._toggle.clicked.connect(self._on_toggle)
        root.addWidget(self._toggle)

        self._panel = RobotTelemetryPanel()
        self._panel.setVisible(False)
        root.addWidget(self._panel)

        self._sync_toggle_text()

    @property
    def telemetry_panel(self) -> RobotTelemetryPanel:
        return self._panel

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._panel.setVisible(expanded)
        self._sync_toggle_text()
        self.expanded_changed.emit(expanded)

    def _on_toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def _sync_toggle_text(self) -> None:
        arrow = "▼" if self._expanded else "▶"
        self._toggle.setText(f"{arrow} 底盘状态详情")
