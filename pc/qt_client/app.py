#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Dict, Set, Tuple

from PyQt5.QtCore import QSettings, QTimer, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from json_client import JsonClientBridge, JsonTcpClient, SEND_RATE_HZ
from widgets import ControlPanel, LogPanel, StatusPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("xtark 底盘 JSON 调试台")
        self.resize(980, 720)

        self.settings = QSettings("xtark", "json_debug_client")
        self.bridge = JsonClientBridge(self)
        self.client = JsonTcpClient(self.bridge)
        self.bridge.log_line.connect(self._on_log)
        self.bridge.message.connect(self._on_message)
        self.bridge.connection_changed.connect(self._on_connection)

        self._pressed_keys: Set[int] = set()
        self._active_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._hold_from_button = False

        self._send_timer = QTimer(self)
        self._send_timer.setInterval(int(1000 / SEND_RATE_HZ))
        self._send_timer.timeout.connect(self._tick_send)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._refresh_status_labels)
        self._ui_timer.start()

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        conn_row = QHBoxLayout()
        conn_row.addWidget(QLabel("Host"))
        self.host_edit = QLineEdit("192.168.1.169")
        conn_row.addWidget(self.host_edit)
        conn_row.addWidget(QLabel("Port"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8765)
        conn_row.addWidget(self.port_spin)
        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.setEnabled(False)
        conn_row.addWidget(self.connect_btn)
        conn_row.addWidget(self.disconnect_btn)
        conn_row.addStretch(1)
        root.addLayout(conn_row)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.control_panel = ControlPanel()
        left_layout.addWidget(self.control_panel)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 3)

        self.log_panel = LogPanel()
        root.addWidget(self.log_panel, 2)

        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.control_panel.velocity_changed.connect(self._on_velocity_from_button)
        self.control_panel.stop_requested.connect(self._stop_motion)

    def _load_settings(self) -> None:
        host = self.settings.value("host", "192.168.1.169")
        port = int(self.settings.value("port", 8765))
        linear = float(self.settings.value("linear_speed", 0.10))
        angular = float(self.settings.value("angular_speed", 0.20))
        self.host_edit.setText(str(host))
        self.port_spin.setValue(port)
        self.control_panel.linear_spin.setValue(linear)
        self.control_panel.angular_spin.setValue(angular)

    def _save_settings(self) -> None:
        self.settings.setValue("host", self.host_edit.text().strip())
        self.settings.setValue("port", self.port_spin.value())
        self.settings.setValue("linear_speed", self.control_panel.linear_speed())
        self.settings.setValue("angular_speed", self.control_panel.angular_speed())

    def _connect(self) -> None:
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        try:
            self.client.connect(host, port)
        except OSError as exc:
            QMessageBox.warning(self, "连接失败", str(exc))
            return
        self._save_settings()
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.host_edit.setEnabled(False)
        self.port_spin.setEnabled(False)

    def _disconnect(self) -> None:
        self._stop_motion()
        self.client.disconnect(send_stop=False)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.host_edit.setEnabled(True)
        self.port_spin.setEnabled(True)

    def _on_connection(self, ok: bool, detail: str) -> None:
        self.status_panel.set_connection(ok, detail)
        if not ok:
            self._pressed_keys.clear()
            self._hold_from_button = False
            self._active_velocity = (0.0, 0.0, 0.0)
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.host_edit.setEnabled(True)
            self.port_spin.setEnabled(True)
            self._send_timer.stop()

    def _on_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append("[{stamp}] {text}".format(stamp=stamp, text=text))

    def _on_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "odom_base":
            self.status_panel.update_odom(msg)
        elif msg_type == "base_status":
            self.status_panel.update_base_status(msg)

    def _on_velocity_from_button(self, lx: float, ly: float, az: float) -> None:
        self._hold_from_button = True
        self._active_velocity = (lx, ly, az)
        self._ensure_send_timer()

    def _stop_motion(self) -> None:
        self._hold_from_button = False
        self._active_velocity = (0.0, 0.0, 0.0)
        if self.client.connected:
            self.client.send_cmd_vel(0.0, 0.0, 0.0)
        if not self._pressed_keys:
            self._send_timer.stop()

    def _ensure_send_timer(self) -> None:
        if self.client.connected and not self._send_timer.isActive():
            self._send_timer.start()

    def _tick_send(self) -> None:
        if not self.client.connected:
            self._send_timer.stop()
            return
        if self._pressed_keys:
            self._active_velocity = self._velocity_from_keys()
        elif not self._hold_from_button:
            self._send_timer.stop()
            return
        lx, ly, az = self._active_velocity
        self.client.send_cmd_vel(lx, ly, az)

    def _velocity_from_keys(self) -> Tuple[float, float, float]:
        linear = self.control_panel.linear_speed()
        angular = self.control_panel.angular_speed()
        lx = ly = az = 0.0
        forward_keys = {
            Qt.Key_W,
            Qt.Key_I,
            Qt.Key_Up,
        }
        back_keys = {Qt.Key_S, Qt.Key_Down}
        left_keys = {Qt.Key_A, Qt.Key_J}
        right_keys = {Qt.Key_D, Qt.Key_L}
        strafe_l_keys = {Qt.Key_Q}
        strafe_r_keys = {Qt.Key_E}

        if self._pressed_keys & forward_keys:
            lx += linear
        if self._pressed_keys & back_keys:
            lx -= linear
        if self._pressed_keys & left_keys:
            az += angular
        if self._pressed_keys & right_keys:
            az -= angular
        if self._pressed_keys & strafe_l_keys:
            ly += linear
        if self._pressed_keys & strafe_r_keys:
            ly -= linear
        return lx, ly, az

    def _refresh_status_labels(self) -> None:
        last_send = "-"
        if self.client.last_send_time > 0:
            last_send = datetime.fromtimestamp(self.client.last_send_time).strftime(
                "%H:%M:%S"
            )
        last_feedback = "-"
        if self.client.last_feedback_time > 0:
            last_feedback = datetime.fromtimestamp(
                self.client.last_feedback_time
            ).strftime("%H:%M:%S")
        self.status_panel.set_control_state(
            self.client.control_state(),
            last_send,
            last_feedback,
        )

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            event.accept()
            return
        key = event.key()
        if key in (Qt.Key_K, Qt.Key_Space):
            self._stop_motion()
            event.accept()
            return
        if key in (
            Qt.Key_W,
            Qt.Key_S,
            Qt.Key_A,
            Qt.Key_D,
            Qt.Key_Q,
            Qt.Key_E,
            Qt.Key_I,
            Qt.Key_J,
            Qt.Key_L,
            Qt.Key_Up,
            Qt.Key_Down,
        ):
            if key not in self._pressed_keys:
                self._pressed_keys.add(key)
                self._hold_from_button = False
                self._active_velocity = self._velocity_from_keys()
                self._ensure_send_timer()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            event.accept()
            return
        key = event.key()
        if key in self._pressed_keys:
            self._pressed_keys.discard(key)
            if self._pressed_keys:
                self._active_velocity = self._velocity_from_keys()
            else:
                self._stop_motion()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def closeEvent(self, event):
        self._save_settings()
        self._stop_motion()
        self.client.disconnect(send_stop=False)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
