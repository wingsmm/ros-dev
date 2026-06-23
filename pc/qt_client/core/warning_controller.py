from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

from core.warning_scan_math import should_warn


@dataclass
class WarningSettings:
    enabled: bool = False
    safemode: bool = True
    beep: bool = True
    min_distance_m: float = 3.0


class WarningController:
    """Client-side warning state aligned with Android WarningSystem + HUDFragment."""

    WARN_AMOUNT_INCR = 0.02
    WARN_AMOUNT_ATTEN = 0.75
    WARN_DELAY_MS = 100
    WARN_RATE_MS = 10
    TONE_DELAY_MS = 300
    DANGER_WARN_AMOUNT = 0.3
    SCAN_STALE_SEC = 1.0

    def __init__(self, settings: Optional[WarningSettings] = None) -> None:
        self.settings = settings or WarningSettings()
        self.warn_amount = 0.0
        self._last_warn_ms = 0.0
        self._last_warn_tick_ms = 0.0
        self._last_beep_ms = 0.0
        self._last_scan_mono = 0.0
        self._front_min_m = float("inf")
        self._speed_mps = 0.0
        self._scan_stale = True

    def apply_settings(self, settings: WarningSettings) -> None:
        self.settings = settings
        if not settings.enabled:
            self.reset()

    def reset(self) -> None:
        self.warn_amount = 0.0
        self._last_warn_ms = 0
        self._last_warn_tick_ms = 0
        self._last_beep_ms = 0

    def on_odom(self, linear_x: float) -> None:
        self._speed_mps = float(linear_x)
        self._decay_warn_amount()

    def on_scan_warning(
        self,
        *,
        front_min_m: float,
        stale: bool,
        stamp_ms: Optional[int] = None,
    ) -> None:
        del stamp_ms  # robot clock; display only, never used for timeout/decay
        now_mono = time.monotonic()
        self._last_scan_mono = now_mono
        self._scan_stale = bool(stale)
        if stale or not math.isfinite(front_min_m):
            self._front_min_m = float("inf")
            return
        self._front_min_m = float(front_min_m)
        self._evaluate_collision(now_mono * 1000.0)

    def touch_scan_timeout(self, now_mono: Optional[float] = None) -> None:
        now_mono = time.monotonic() if now_mono is None else now_mono
        if self._last_scan_mono <= 0.0:
            self._scan_stale = True
            return
        if now_mono - self._last_scan_mono > self.SCAN_STALE_SEC:
            self._scan_stale = True
            self._front_min_m = float("inf")

    def _evaluate_collision(self, now_ms: float) -> None:
        if self._scan_stale:
            return
        if not should_warn(
            self._front_min_m,
            enabled=self.settings.enabled,
            speed_mps=self._speed_mps,
            min_range_m=max(0.2, self.settings.min_distance_m),
        ):
            return
        if now_ms - self._last_warn_tick_ms < self.WARN_RATE_MS:
            return
        self._last_warn_tick_ms = now_ms
        self.warn_amount = min(1.0, self.warn_amount + self.WARN_AMOUNT_INCR)
        self._last_warn_ms = now_ms

    def _decay_warn_amount(self) -> None:
        if self.warn_amount <= 0.0:
            return
        now_ms = time.monotonic() * 1000.0
        if now_ms - self._last_warn_ms > self.WARN_DELAY_MS:
            self.warn_amount *= self.WARN_AMOUNT_ATTEN
            if self.warn_amount < 0.05:
                self.warn_amount = 0.0

    def forward_scale(self, linear_x: float) -> float:
        if not self.settings.enabled or not self.settings.safemode:
            return 1.0
        if linear_x < 0.0:
            return 1.0
        return float(math.pow(1.0 - self.warn_amount, 2.0))

    def should_beep(self, now_ms: Optional[float] = None) -> bool:
        if not self.settings.enabled or not self.settings.beep:
            return False
        if self.warn_amount <= self.DANGER_WARN_AMOUNT:
            return False
        if self._speed_mps <= 0.01:
            return False
        now_ms = time.monotonic() * 1000.0 if now_ms is None else now_ms
        if now_ms - self._last_beep_ms < self.TONE_DELAY_MS:
            return False
        self._last_beep_ms = now_ms
        return True

    @property
    def scan_stale(self) -> bool:
        return self._scan_stale
