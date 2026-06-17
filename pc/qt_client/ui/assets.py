from __future__ import annotations

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "android"


def android_asset(name: str) -> str:
    return str(_ASSETS_DIR / name)
