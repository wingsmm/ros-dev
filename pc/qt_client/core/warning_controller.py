from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

from core.warning_scan_math import should_warn

logger = logging.getLogger(__name__)


@dataclass
class WarningSettings:
    enabled: bool = False
    safemode: bool = True
    beep: bool = True
    min_distance_m: float = 3.0
    front_half_angle_deg: float = 40.0
    min_valid_range_m: float = 0.25


class WarningController:
    """Client-side warning state for Qt manual collision warning."""

    WARN_RATE_MS = 10
    WARN_ATTACK_ALPHA = 0.45
    WARN_RELEASE_ALPHA = 0.22
    WARN_ZERO_EPSILON = 0.02
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
        self._logged_stale = False
        self._last_state_log_ms = 0.0

    def apply_settings(self, settings: WarningSettings) -> None:
        self.settings = settings
        if not settings.enabled:
            self.reset()

    def reset(self) -> None:
        self.warn_amount = 0.0
        self._last_warn_ms = 0
        self._last_warn_tick_ms = 0
        self._last_beep_ms = 0
        self._logged_stale = False

    def on_odom(self, linear_x: float) -> None:
        self._speed_mps = float(linear_x)

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
        if not stale:
            self._logged_stale = False
        if stale or not math.isfinite(front_min_m):
            self._front_min_m = float("inf")
            self._smooth_warn_amount(0.0)
            return
        self._front_min_m = float(front_min_m)
        self._evaluate_collision(now_mono * 1000.0)

    def touch_scan_timeout(self, now_mono: Optional[float] = None) -> bool:
        """Mark scan stale after timeout; returns True when stale state is newly entered."""
        now_mono = time.monotonic() if now_mono is None else now_mono
        if self._last_scan_mono <= 0.0:
            if not self._scan_stale:
                self._scan_stale = True
                return True
            return False
        if now_mono - self._last_scan_mono > self.SCAN_STALE_SEC:
            if not self._scan_stale:
                self._scan_stale = True
                self._front_min_m = float("inf")
                self._smooth_warn_amount(0.0)
                if not self._logged_stale:
                    logger.info("warning scan stale")
                    self._logged_stale = True
                return True
            self._scan_stale = True
            self._front_min_m = float("inf")
            self._smooth_warn_amount(0.0)
        return False

    def _evaluate_collision(self, now_ms: float) -> None:
        if self._scan_stale:
            return
        threshold = self.warning_threshold_m
        warning = should_warn(
            self._front_min_m,
            enabled=self.settings.enabled,
            speed_mps=self._speed_mps,
            min_range_m=threshold,
            min_valid_range=self.settings.min_valid_range_m,
        )
        if now_ms - self._last_warn_tick_ms < self.WARN_RATE_MS:
            return
        self._last_warn_tick_ms = now_ms
        target = self._target_warn_amount(threshold) if warning else 0.0
        self._smooth_warn_amount(target)
        if warning:
            self._last_warn_ms = now_ms
        self._log_state(
            now_ms,
            threshold=threshold,
            warning=warning,
            target=target,
        )

    def _target_warn_amount(self, threshold: float) -> float:
        if threshold <= 0.0 or not math.isfinite(self._front_min_m):
            return 0.0
        return 1.0 - max(0.0, min(1.0, self._front_min_m / threshold))

    def _smooth_warn_amount(self, target: float) -> None:
        target = max(0.0, min(1.0, float(target)))
        alpha = (
            self.WARN_ATTACK_ALPHA
            if target > self.warn_amount
            else self.WARN_RELEASE_ALPHA
        )
        self.warn_amount += (target - self.warn_amount) * alpha
        if self.warn_amount < self.WARN_ZERO_EPSILON:
            self.warn_amount = 0.0

    def _log_state(
        self,
        now_ms: float,
        *,
        threshold: float,
        warning: bool,
        target: float,
    ) -> None:
        if now_ms - self._last_state_log_ms < 2000.0:
            return
        self._last_state_log_ms = now_ms
        logger.info(
            "warning state: warning=%s front=%.2f threshold=%.2f "
            "speed=%.3f target=%.2f warn=%.2f scale=%.2f stale=%s",
            warning,
            self._front_min_m,
            threshold,
            self._speed_mps,
            target,
            self.warn_amount,
            self.forward_scale(1.0),
            self._scan_stale,
        )

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

    @property
    def front_min_m(self) -> float:
        return self._front_min_m

    @property
    def warning_threshold_m(self) -> float:
        return max(0.2, self.settings.min_distance_m)
