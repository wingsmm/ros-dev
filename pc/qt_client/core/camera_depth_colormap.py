"""Raw depth -> RGB preview (PC/Qt, no xtark /camera/depth/preview)."""

from __future__ import annotations

from typing import Tuple

import numpy as np

from core.camera_depth_frame import DepthFrame, DepthFrameStats

DEFAULT_MIN_DEPTH_M = 0.2
DEFAULT_MAX_DEPTH_M = 5.0


def _decode_depth_array(
    raw,
    *,
    width: int,
    height: int,
    encoding: str,
) -> np.ndarray:
    enc = (encoding or "").lower()
    if enc in ("16uc1", "mono16"):
        arr = np.frombuffer(raw, dtype=np.uint16)
        if arr.size < width * height:
            raise ValueError(f"16UC1 buffer too small: {arr.size} < {width * height}")
        depth_mm = arr[: width * height].reshape((height, width))
        depth_m = depth_mm.astype(np.float32) / 1000.0
        depth_m[depth_mm == 0] = np.nan
        return depth_m
    if enc in ("32fc1",):
        arr = np.frombuffer(raw, dtype=np.float32)
        if arr.size < width * height:
            raise ValueError(f"32FC1 buffer too small: {arr.size} < {width * height}")
        depth_m = arr[: width * height].reshape((height, width)).astype(np.float32)
        depth_m[~np.isfinite(depth_m)] = np.nan
        depth_m[depth_m <= 0.0] = np.nan
        return depth_m
    raise ValueError(f"unsupported depth encoding: {encoding}")


def _apply_jet(norm_u8: np.ndarray) -> np.ndarray:
    """Map HxW uint8 -> HxWx3 uint8 RGB (jet-like)."""
    v = norm_u8.astype(np.float32) / 255.0
    r = np.clip(1.5 - np.abs(4.0 * v - 3.0), 0.0, 1.0)
    g = np.clip(1.5 - np.abs(4.0 * v - 2.0), 0.0, 1.0)
    b = np.clip(1.5 - np.abs(4.0 * v - 1.0), 0.0, 1.0)
    return (np.stack([r, g, b], axis=-1) * 255.0).astype(np.uint8)


def compute_depth_stats(
    depth_m: np.ndarray,
    *,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    max_depth_m: float = DEFAULT_MAX_DEPTH_M,
) -> DepthFrameStats:
    valid = np.isfinite(depth_m) & (depth_m >= min_depth_m) & (depth_m <= max_depth_m)
    total = depth_m.size
    valid_count = int(valid.sum())
    ratio = (valid_count / total) if total else 0.0

    center_m = 0.0
    h, w = depth_m.shape
    cy, cx = h // 2, w // 2
    cval = depth_m[cy, cx]
    if np.isfinite(cval) and cval > 0:
        center_m = float(cval)

    nearest_m = 0.0
    if valid_count:
        nearest_m = float(np.nanmin(depth_m[valid]))

    vmin = vmax = 0.0
    if valid_count:
        vmin = float(np.nanmin(depth_m[valid]))
        vmax = float(np.nanmax(depth_m[valid]))

    return DepthFrameStats(
        center_distance_m=center_m,
        nearest_valid_m=nearest_m,
        valid_ratio=ratio,
        min_depth_m=vmin,
        max_depth_m=vmax,
    )


def depth_meters_to_rgb(
    depth_m: np.ndarray,
    *,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    max_depth_m: float = DEFAULT_MAX_DEPTH_M,
) -> np.ndarray:
    """Return HxWx3 uint8 RGB; invalid pixels are black."""
    valid = np.isfinite(depth_m) & (depth_m > 0.0)
    norm = np.zeros(depth_m.shape, dtype=np.uint8)
    if valid.any():
        clipped = np.clip(depth_m, min_depth_m, max_depth_m)
        span = max(max_depth_m - min_depth_m, 1e-6)
        norm[valid] = (
            ((clipped[valid] - min_depth_m) / span) * 255.0
        ).astype(np.uint8)
    rgb = _apply_jet(norm)
    rgb[~valid] = 0
    return rgb


def ros_image_to_depth_frame(
    *,
    data,
    width: int,
    height: int,
    encoding: str,
    timestamp_ns: int,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    max_depth_m: float = DEFAULT_MAX_DEPTH_M,
    camera_info_online: bool = False,
    fps: float = 0.0,
    latency_ms: float = 0.0,
) -> Tuple[DepthFrame, np.ndarray]:
    depth_m = _decode_depth_array(
        data, width=width, height=height, encoding=encoding
    )
    stats = compute_depth_stats(
        depth_m, min_depth_m=min_depth_m, max_depth_m=max_depth_m
    )
    stats = DepthFrameStats(
        center_distance_m=stats.center_distance_m,
        nearest_valid_m=stats.nearest_valid_m,
        valid_ratio=stats.valid_ratio,
        min_depth_m=stats.min_depth_m,
        max_depth_m=stats.max_depth_m,
        fps=fps,
        latency_ms=latency_ms,
        encoding=encoding,
        camera_info_online=camera_info_online,
    )
    rgb = depth_meters_to_rgb(
        depth_m, min_depth_m=min_depth_m, max_depth_m=max_depth_m
    )
    frame = DepthFrame(
        width=width,
        height=height,
        encoding=encoding,
        timestamp_ns=timestamp_ns,
        stats=stats,
        depth_meters=depth_m,
    )
    return frame, rgb


def downscale_rgb(rgb: np.ndarray, factor: int) -> np.ndarray:
    """Decimate preview RGB for display (stats should use full resolution)."""
    factor = max(1, int(factor))
    if factor <= 1:
        return rgb
    return rgb[::factor, ::factor].copy()
