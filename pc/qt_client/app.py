#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
from datetime import datetime
from typing import Any, Dict, Set, Tuple

from PyQt5.QtCore import QDir, QLockFile, QSettings, QTimer, Qt
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

from gateway.json_client import JsonClientBridge, JsonTcpClient, SEND_RATE_HZ
from mapping.ros_stack import RosStackManager
from ui.fonts import setup_app_font
from ui.widgets import CameraPanel, ControlPanel, LogPanel, NavPanel, StackPanel, StatusPanel

APP_TITLE = "xtark Console"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xtark WSL2 client")
    parser.add_argument(
        "--no-ros",
        action="store_true",
        help="JSON/GUI only; disable ROS2 publishing and mapping controls",
    )
    return parser.parse_args()


class MainWindow(QMainWindow):
    def __init__(self, enable_ros2: bool = True):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(980, 820)

        self._ros2 = None
        if enable_ros2:
            from gateway.ros2_pub import ros2_unavailable_reason, try_create

            self._ros2 = try_create()
            if self._ros2 is None:
                reason = ros2_unavailable_reason()
                print("WARN: ROS2 publish unavailable:", reason or "unknown")
                self._ros2_fail_reason = reason or "初始化失败"
            else:
                self._ros2_fail_reason = ""
                self._ros2.set_cmd_vel_callback(self._forward_nav_cmd_vel)
        else:
            self._ros2_fail_reason = "已禁用 (--no-ros)"

        self.settings = QSettings("xtark", "json_debug_client")
        self.bridge = JsonClientBridge(self)
        self.client = JsonTcpClient(self.bridge)
        self.bridge.log_line.connect(self._on_log)
        self.bridge.message.connect(self._on_message)
        self.bridge.connection_changed.connect(self._on_connection)

        self._stack = RosStackManager(log=self._on_log) if enable_ros2 else None

        self._pressed_keys: Set[int] = set()
        self._active_velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._hold_from_button = False
        self._nav_cmd_paused = False
        self._cleanup_done = False

        self._send_timer = QTimer(self)
        self._send_timer.setInterval(int(1000 / SEND_RATE_HZ))
        self._send_timer.timeout.connect(self._tick_send)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._refresh_status_labels)
        self._ui_timer.start()

        if self._ros2 is not None:
            self._ros_timer = QTimer(self)
            self._ros_timer.setInterval(50)
            self._ros_timer.timeout.connect(self._ros2_spin)
            self._ros_timer.start()

        if self._stack is not None:
            self._stack_timer = QTimer(self)
            self._stack_timer.setInterval(500)
            self._stack_timer.timeout.connect(self._refresh_stack_status)
            self._stack_timer.start()

        self._build_ui()
        self._load_settings()

    def _ros2_spin(self) -> None:
        if self._ros2 is None:
            return
        try:
            self._ros2.spin_once()
        except Exception as exc:
            print("WARN: ROS2 spin stopped:", exc)
            self._ros2 = None
            if hasattr(self, "_ros_timer"):
                self._ros_timer.stop()

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
        self.stack_panel = StackPanel()
        stack_ok = self._stack is not None
        self.stack_panel.setEnabled(stack_ok)
        if stack_ok:
            self.stack_panel.set_ros2_status(
                self._ros2 is not None,
                getattr(self, "_ros2_fail_reason", ""),
            )
        left_layout.addWidget(self.stack_panel)
        self.nav_panel = NavPanel()
        self.nav_panel.setEnabled(stack_ok)
        left_layout.addWidget(self.nav_panel)
        left_layout.addStretch(1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)
        self.camera_panel = CameraPanel()
        self.camera_panel.log.connect(self._on_log)
        right_layout.addWidget(self.camera_panel)
        right_layout.addStretch(1)
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

        if self._stack is not None:
            self.stack_panel.start_rviz.connect(lambda: self._run_stack("start", "rviz2"))
            self.stack_panel.stop_rviz.connect(lambda: self._run_stack("stop", "rviz2"))
            self.stack_panel.start_slam.connect(lambda: self._run_stack("start", "slam"))
            self.stack_panel.stop_slam.connect(lambda: self._run_stack("stop", "slam"))
            self.stack_panel.start_all.connect(lambda: self._run_stack("start", "all"))
            self.stack_panel.stop_all.connect(lambda: self._run_stack("stop", "all"))
            self.stack_panel.save_map.connect(self._save_map)
            self.nav_panel.start_localization.connect(self._start_localization)
            self.nav_panel.stop_localization.connect(
                lambda: self._stop_nav_part("localization")
            )
            self.nav_panel.start_navigation.connect(self._start_navigation)
            self.nav_panel.stop_navigation.connect(
                lambda: self._stop_nav_part("navigation")
            )
            self.nav_panel.start_nav_all.connect(self._start_nav_all)
            self.nav_panel.stop_nav_all.connect(self._stop_nav_all)
            self.nav_panel.emergency_stop.connect(self._emergency_stop)

    def _load_settings(self) -> None:
        host = self.settings.value("host", "192.168.1.169")
        port = int(self.settings.value("port", 8765))
        linear = float(self.settings.value("linear_speed", 0.10))
        angular = float(self.settings.value("angular_speed", 0.20))
        self.host_edit.setText(str(host))
        self.port_spin.setValue(port)
        self.control_panel.linear_spin.setValue(linear)
        self.control_panel.angular_spin.setValue(angular)
        self.camera_panel.load_settings(self.settings)
        map_yaml = str(self.settings.value("map_yaml", ""))
        if map_yaml:
            self.nav_panel.set_map_yaml(map_yaml)

    def _save_settings(self) -> None:
        self.settings.setValue("host", self.host_edit.text().strip())
        self.settings.setValue("port", self.port_spin.value())
        self.settings.setValue("linear_speed", self.control_panel.linear_speed())
        self.settings.setValue("angular_speed", self.control_panel.angular_speed())
        self.settings.setValue("map_yaml", self.nav_panel.map_yaml())
        self.camera_panel.save_settings(self.settings)

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
        if self._ros2 is not None and self._stack is not None:
            self._ros2.set_nav_cmd_enabled(
                ok and self._stack.is_nav_running()
            )

    def _on_log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append("[{stamp}] {text}".format(stamp=stamp, text=text))

    def _on_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "odom_base":
            self.status_panel.update_odom(msg)
        elif msg_type == "base_status":
            self.status_panel.update_base_status(msg)
        if self._ros2 is not None:
            self._ros2.on_json(msg)

    def _run_stack(self, action: str, target: str) -> None:
        if self._stack is None:
            return
        if action == "start" and target == "rviz2":
            self._stack.start_rviz()
        elif action == "start" and target == "slam":
            self._stack.start_slam()
        elif action == "start" and target == "all":
            self._stack.start_all()
        elif action == "stop" and target == "all":
            self._stack.stop_all()
        else:
            self._stack.stop(target)
        self._refresh_stack_status()

    def _refresh_stack_status(self) -> None:
        if self._stack is None:
            return
        self.stack_panel.set_rviz_running(self._stack.is_running("rviz2"))
        self.stack_panel.set_slam_running(self._stack.is_running("slam"))
        nav_active = self._stack.is_nav_running()
        if not nav_active:
            self._nav_cmd_paused = False
        self.nav_panel.set_localization_running(self._stack.is_running("localization"))
        self.nav_panel.set_navigation_running(self._stack.is_running("navigation"))
        self.nav_panel.set_nav_active(nav_active)
        self._set_manual_control_enabled(not nav_active)
        if self._ros2 is not None:
            self._ros2.set_nav_cmd_enabled(
                nav_active and self.client.connected and not self._nav_cmd_paused
            )

    def _set_manual_control_enabled(self, enabled: bool) -> None:
        self.control_panel.setEnabled(enabled)

    def _forward_nav_cmd_vel(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> None:
        if not self.client.connected:
            return
        self.client.send_cmd_vel(
            linear_x, linear_y, angular_z, log_tx=False
        )

    def _start_localization(self) -> None:
        if self._stack is None:
            return
        ok, detail = self._stack.start_localization(self.nav_panel.map_yaml())
        if ok:
            self._nav_cmd_paused = False
            self.nav_panel.set_map_yaml(detail)
            self._save_settings()
        else:
            QMessageBox.warning(self, "启动定位", detail)
        self._refresh_stack_status()

    def _start_navigation(self) -> None:
        if self._stack is None:
            return
        if not self._stack.is_running("localization"):
            QMessageBox.warning(self, "启动 Nav2", "请先启动定位。")
            return
        self._nav_cmd_paused = False
        if not self._stack.start_navigation():
            QMessageBox.warning(self, "启动 Nav2", "启动失败，见日志面板。")
        self._refresh_stack_status()

    def _start_nav_all(self) -> None:
        if self._stack is None:
            return
        if not self.client.connected:
            QMessageBox.warning(self, "启动导航栈", "请先连接 xtark。")
            return
        ok, detail = self._stack.start_nav_all(self.nav_panel.map_yaml())
        if ok:
            self._nav_cmd_paused = False
            self.nav_panel.set_map_yaml(detail)
            self._save_settings()
            if not self._stack.is_running("rviz2"):
                self._stack.start_rviz()
        else:
            QMessageBox.warning(self, "启动导航栈", detail)
        self._refresh_stack_status()

    def _stop_nav_part(self, name: str) -> None:
        if self._stack is None:
            return
        if name == "navigation":
            self._stack.cancel_navigation()
        self._stack.stop(name)
        self._stop_motion()
        self._refresh_stack_status()

    def _stop_nav_all(self) -> None:
        if self._stack is None:
            return
        self._nav_cmd_paused = False
        self._stack.cancel_navigation()
        self._stack.stop_nav()
        self._stop_motion()
        self._refresh_stack_status()

    def _emergency_stop(self) -> None:
        self._pressed_keys.clear()
        self._hold_from_button = False
        self._active_velocity = (0.0, 0.0, 0.0)
        self._nav_cmd_paused = True
        if self._ros2 is not None:
            self._ros2.set_nav_cmd_enabled(False)
        if self.client.connected:
            self.client.send_cmd_vel(0.0, 0.0, 0.0)
        if self._stack is not None:
            self._stack.cancel_navigation()

    def _save_map(self) -> None:
        if self._stack is None:
            return
        ok, message = self._stack.save_map(self.stack_panel.map_name())
        if ok:
            QMessageBox.information(self, "保存地图", message)
            for line in message.splitlines():
                if line.endswith(".yaml"):
                    self.nav_panel.set_map_yaml(line)
                    self._save_settings()
                    break
        else:
            QMessageBox.warning(self, "保存地图", message)

    def _on_velocity_from_button(self, lx: float, ly: float, az: float) -> None:
        if self._stack is not None and self._stack.is_nav_running():
            return
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
        forward_keys = {Qt.Key_W, Qt.Key_I, Qt.Key_Up}
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
            self._emergency_stop()
            event.accept()
            return
        if self._stack is not None and self._stack.is_nav_running():
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

    def cleanup(self) -> None:
        if self._cleanup_done:
            return
        self._cleanup_done = True
        if hasattr(self, "_ros_timer"):
            self._ros_timer.stop()
        if hasattr(self, "_stack_timer"):
            self._stack_timer.stop()
        self._send_timer.stop()
        self._ui_timer.stop()
        self._save_settings()
        self.camera_panel.shutdown()
        self._stop_motion()
        self.client.disconnect(send_stop=False)
        if self._stack is not None:
            self._stack.cancel_navigation()
            self._stack.stop_all()
        if self._ros2 is not None:
            self._ros2.set_nav_cmd_enabled(False)
        if self._ros2 is not None:
            self._ros2.shutdown()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


def main() -> int:
    args = parse_args()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    setup_app_font(app)
    lock = QLockFile(QDir.tempPath() + "/xtark_console.lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, APP_TITLE, "xtark Console is already running.")
        return 1
    window = MainWindow(enable_ros2=not args.no_ros)
    app.aboutToQuit.connect(window.cleanup)
    signal.signal(signal.SIGINT, lambda *_args: window.close())
    signal.signal(signal.SIGTERM, lambda *_args: window.close())
    signal_timer = QTimer()
    signal_timer.setInterval(500)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()
    window.show()
    result = app.exec_()
    signal_timer.stop()
    lock.unlock()
    return result


if __name__ == "__main__":
    sys.exit(main())
