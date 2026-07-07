#!/usr/bin/env python3
"""Jetson cockpit Qt entry point.

Runs on PC/WSL only. It publishes dry-run /cmd_vel commands and listens for
the Jetson-side /vehicle/control_action echo.
"""

from __future__ import annotations

import os
import sys

from PyQt5.QtWidgets import QApplication
from core.config import load_config
from core.logging_config import setup_logging
from main_window import MainWindow


def main() -> int:
    cfg = load_config()
    os.environ["ROS_DOMAIN_ID"] = cfg.ros_domain_id
    log_path = setup_logging(cfg.log_dir, cfg.log_level)

    app = QApplication(sys.argv)
    app.setApplicationName("Jetson Qt 控制台")

    window = MainWindow(cfg, log_path)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
