"""Depth frame data structures for PC-side preview (Phase 1.5)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DepthSourceKind(str, Enum):
    RAW_HTTP = "raw_http"
    OFFLINE = "offline"


@dataclass(frozen=True)
class DepthFrameStats:
  """Aggregated depth metrics for UI panel."""

  center_distance_m: float = 0.0
  nearest_valid_m: float = 0.0
  valid_ratio: float = 0.0
  min_depth_m: float = 0.0
  max_depth_m: float = 0.0
  fps: float = 0.0
  latency_ms: float = 0.0
  encoding: str = ""
  camera_info_online: bool = False


@dataclass(frozen=True)
class DepthFrame:
  """One decoded depth image + derived metrics."""

  width: int
  height: int
  encoding: str
  timestamp_ns: int
  stats: DepthFrameStats
  # Normalized depth in meters (float32); invalid pixels are NaN.
  depth_meters: object  # numpy.ndarray — avoid hard import at module load
