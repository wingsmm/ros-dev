from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

_MAX_RANGE_COUNT = 4096
_PARSE_ERROR_INTERVAL_SEC = 5.0
_last_parse_error_log = 0.0

logger = logging.getLogger(__name__)


def _log_parse_error(message: str) -> None:
    global _last_parse_error_log
    now = time.monotonic()
    if now - _last_parse_error_log < _PARSE_ERROR_INTERVAL_SEC:
        return
    _last_parse_error_log = now
    logger.warning(message)


def _clean_range(
    value: Any,
    range_min: float,
    range_max: float,
) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number < range_min or number > range_max:
        return None
    return number


@dataclass(frozen=True)
class LaserScanFrame:
    stamp_ms: int
    frame_id: str
    angle_min: float
    angle_max: float
    angle_increment: float
    range_min: float
    range_max: float
    ranges: Tuple[Optional[float], ...]

    @classmethod
    def from_message(
        cls,
        msg: Dict[str, Any],
        *,
        reverse: bool = False,
        display_stride: int = 1,
    ) -> Optional["LaserScanFrame"]:
        required = (
            "stamp_ms",
            "angle_min",
            "angle_max",
            "angle_increment",
            "range_min",
            "range_max",
            "ranges",
        )
        for key in required:
            if key not in msg:
                _log_parse_error(f"missing field: {key}")
                return None

        try:
            stamp_ms = int(msg["stamp_ms"])
            angle_min = float(msg["angle_min"])
            source_angle_max = float(msg["angle_max"])
            angle_increment = float(msg["angle_increment"])
            range_min = float(msg["range_min"])
            range_max = float(msg["range_max"])
            raw_ranges = msg["ranges"]
        except (TypeError, ValueError):
            _log_parse_error("numeric field parse failed")
            return None

        if not all(
            math.isfinite(value)
            for value in (
                angle_min,
                source_angle_max,
                angle_increment,
                range_min,
                range_max,
            )
        ):
            _log_parse_error("non-finite scan metadata")
            return None
        if angle_increment <= 0.0:
            _log_parse_error("invalid angle_increment")
            return None
        if range_min < 0.0 or range_max <= range_min:
            _log_parse_error("invalid range bounds")
            return None
        if not isinstance(raw_ranges, (list, tuple)):
            _log_parse_error("ranges is not a list")
            return None
        if len(raw_ranges) > _MAX_RANGE_COUNT:
            _log_parse_error(f"ranges too large: {len(raw_ranges)}")
            return None

        try:
            stride = max(1, int(display_stride))
        except (TypeError, ValueError):
            _log_parse_error("invalid display_stride")
            return None

        sliced = raw_ranges[::stride]
        cleaned = tuple(
            _clean_range(value, range_min, range_max) for value in sliced
        )
        if reverse:
            cleaned = tuple(reversed(cleaned))

        eff_increment = angle_increment * stride
        angle_max = angle_min + eff_increment * max(len(cleaned) - 1, 0)

        return cls(
            stamp_ms=stamp_ms,
            frame_id=str(msg.get("frame_id") or "laser"),
            angle_min=angle_min,
            angle_max=angle_max,
            angle_increment=eff_increment,
            range_min=range_min,
            range_max=range_max,
            ranges=cleaned,
        )

    def iter_valid_points(
        self,
    ) -> Iterable[Tuple[float, float, float]]:
        """Yield (angle_rad, local_x, local_y) for valid ranges."""
        angle = self.angle_min
        for distance in self.ranges:
            if distance is not None:
                local_x = distance * math.cos(angle)
                local_y = distance * math.sin(angle)
                yield angle, local_x, local_y
            angle += self.angle_increment
