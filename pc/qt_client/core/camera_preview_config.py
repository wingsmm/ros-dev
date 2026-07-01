"""Qt camera viewport preview toggle (data taps / bridge unaffected)."""

from __future__ import annotations

import os


def camera_qt_preview_enabled() -> bool:
    value = os.environ.get("CAMERA_QT_PREVIEW_ENABLE", "1").strip().lower()
    return value not in ("0", "false", "no", "off")
