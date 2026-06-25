"""DEPRECATED: legacy Qt debug window package.

Do not add new features under pc/qt_client/legacy/. The default entry is the new
robot shell (ui/). Legacy remains only as a gated fallback for historical ROS2
debug comparison.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from legacy.legacy_window import LegacyWindow

__all__ = ["LegacyWindow"]


def __getattr__(name: str):
    if name == "LegacyWindow":
        from legacy.legacy_window import LegacyWindow

        return LegacyWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
