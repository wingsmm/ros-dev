#!/usr/bin/env python3
import logging
import sys

from PyQt5.QtWidgets import QApplication

from core.logging_config import install_excepthook, setup_logging, shutdown_logging
from main_window import MainWindow

logger = logging.getLogger(__name__)


def main():
    settings = setup_logging()
    install_excepthook()
    logger.info(
        "starting VMware Qt RViz Console log_dir=%s level=%s file_logging=%s",
        settings.log_dir,
        settings.level,
        settings.file_logging_enabled,
    )

    app = QApplication(sys.argv)
    app.setApplicationName("VMware Qt RViz Console")
    app.aboutToQuit.connect(shutdown_logging)
    win = MainWindow(settings)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
