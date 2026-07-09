"""Small logging setup for Jetson cockpit."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging(log_dir: Path, level: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / ("jetson-cockpit-%s.log" % date.today().isoformat())
    log_level = level if level in _VALID_LEVELS else "INFO"

    root = logging.getLogger()
    root.handlers = []
    root.setLevel(getattr(logging, log_level))

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    return log_path


def new_child_log_path(prefix: str = "child") -> Path:
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / ("%s-%s.log" % (prefix, stamp))
