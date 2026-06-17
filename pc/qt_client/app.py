#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys

from PyQt5.QtCore import QDir, QLockFile, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from main_window import APP_TITLE, create_main_window
from ui.fonts import setup_app_font


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xtark WSL2 client")
    parser.add_argument(
        "--no-ros",
        action="store_true",
        help="JSON/GUI only; disable ROS2 publishing and mapping controls",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy debug dashboard layout (old MainWindow UI)",
    )
    return parser.parse_args()


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

    if args.legacy:
        window = create_main_window(enable_ros2=not args.no_ros, legacy_ui=True)
    else:
        window = create_main_window(enable_ros2=False, legacy_ui=False)

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
