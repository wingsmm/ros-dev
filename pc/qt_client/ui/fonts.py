"""Pick a CJK-capable font for PyQt5 on WSL2."""

from __future__ import annotations

import os
from typing import Iterable, List

from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication


def _existing(paths: Iterable[str]) -> List[str]:
    return [path for path in paths if os.path.isfile(path)]


def setup_app_font(app: QApplication, point_size: int = 10) -> str:
    """Apply a Chinese-capable font. Returns the family name used."""
    os.environ.setdefault("LANG", "C.UTF-8")

    # WSL2: reuse Windows fonts (most reliable).
    win_fonts = _existing(
        [
            "/mnt/c/Windows/Fonts/msyh.ttc",      # Microsoft YaHei
            "/mnt/c/Windows/Fonts/msyhbd.ttc",
            "/mnt/c/Windows/Fonts/simhei.ttf",    # SimHei
            "/mnt/c/Windows/Fonts/simsun.ttc",    # SimSun
        ]
    )
    for path in win_fonts:
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], point_size))
            return families[0]

    # Linux packages: fonts-noto-cjk / fonts-wqy-microhei
    for family in (
        "Noto Sans CJK SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Droid Sans Fallback",
    ):
        if family in QFontDatabase().families():
            app.setFont(QFont(family, point_size))
            return family

    return QApplication.font(app).family()
