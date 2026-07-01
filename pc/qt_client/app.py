#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from PyQt5.QtCore import QDir, QLockFile, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

from core.logging_config import install_excepthook, setup_logging, shutdown_logging
from core.ros2_runtime import boot_ros2_runtime
from main_window import APP_TITLE, create_main_window
from ui.fonts import setup_app_font

logger = logging.getLogger(__name__)

_LEGACY_ENV_OK = frozenset({"1", "true", "yes", "on"})


def _load_local_env() -> None:
    """Load pc/qt_client/.env into process env without overriding exports."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _legacy_entry_allowed() -> bool:
    return os.environ.get("XTARK_ALLOW_LEGACY", "").strip().lower() in _LEGACY_ENV_OK


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
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def _reject_legacy_without_env() -> int:
    logger.error("legacy UI blocked; set XTARK_ALLOW_LEGACY=1 to use --legacy")
    print(
        "ERROR: legacy debug window is deprecated. "
        "Set XTARK_ALLOW_LEGACY=1 only when you must compare old behavior.",
        file=sys.stderr,
    )
    shutdown_logging()
    return 2


def main() -> int:
    _load_local_env()
    args = parse_args()

    if args.legacy and not _legacy_entry_allowed():
        setup_logging()
        return _reject_legacy_without_env()

    settings = setup_logging()
    install_excepthook()

    ros2_enabled = not args.no_ros
    ros2_status = boot_ros2_runtime(enabled=ros2_enabled)

    logger.info(
        "starting %s legacy=%s no_ros=%s log_dir=%s level=%s "
        "odom_log=%s odom_interval=%.1fs file_logging=%s",
        APP_TITLE,
        args.legacy,
        args.no_ros,
        settings.log_dir,
        settings.level,
        settings.odom_log_enabled,
        settings.odom_log_interval_sec,
        settings.file_logging_enabled,
    )

    if ros2_enabled and not ros2_status.bridge_ready:
        logger.warning(
            "ROS2 bridge not ready at boot (robot page panel will show details):\n%s",
            ros2_status.format_report(),
        )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    setup_app_font(app)

    lock = QLockFile(QDir.tempPath() + "/xtark_console.lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.warning(None, APP_TITLE, "xtark Console is already running.")
        logger.warning("second instance blocked by lock file")
        shutdown_logging()
        return 1

    if args.legacy:
        logger.warning(
            "DEPRECATED: starting legacy debug window; "
            "do not add new features here; use the new robot shell"
        )
        window = create_main_window(enable_ros2=not args.no_ros, legacy_ui=True)
    else:
        window = create_main_window(enable_ros2=False, legacy_ui=False)

    quitting = {"active": False}

    def _request_quit() -> None:
        if quitting["active"]:
            return
        quitting["active"] = True
        logger.info("quit requested (signal or platform)")
        window.cleanup()
        app.quit()

    app.aboutToQuit.connect(window.cleanup)
    signal.signal(signal.SIGINT, lambda *_args: QTimer.singleShot(0, _request_quit))
    signal.signal(signal.SIGTERM, lambda *_args: QTimer.singleShot(0, _request_quit))

    signal_timer = QTimer()
    signal_timer.setInterval(500)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()

    window.show()
    result = app.exec_()
    signal_timer.stop()
    lock.unlock()
    logger.info("exiting with code %s", result)
    shutdown_logging()
    return result


if __name__ == "__main__":
    sys.exit(main())
