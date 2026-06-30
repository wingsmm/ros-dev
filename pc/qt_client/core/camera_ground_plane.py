"""Depth-based ground plane estimation for the camera perception view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.camera_ground_config import GroundPerceptionConfig
from core.camera_ground_geometry import GroundPerceptionGeometry, Point3D


@dataclass(frozen=True)
class GroundPlaneEstimate:
    """Camera-optical ground plane: normal.dot(point) + offset = 0."""

    normal: tuple[float, float, float]
    offset: float
    inlier_ratio: float
    sample_count: int
    inlier_count: int
    rms_error_m: float
    valid: bool
    reason: str = ""


def _normalize(v: np.ndarray) -> np.ndarray:
    return v / max(float(np.linalg.norm(v)), 1e-9)


def _expected_ground_plane(config: GroundPerceptionConfig) -> tuple[np.ndarray, float]:
    geometry = GroundPerceptionGeometry(config)
    p0 = geometry.base_to_camera(Point3D(1.0, 0.0, 0.0))
    p1 = geometry.base_to_camera(Point3D(2.0, 0.0, 0.0))
    p2 = geometry.base_to_camera(Point3D(1.0, 0.5, 0.0))
    a = np.array([p0.x, p0.y, p0.z], dtype=np.float64)
    b = np.array([p1.x, p1.y, p1.z], dtype=np.float64)
    c = np.array([p2.x, p2.y, p2.z], dtype=np.float64)
    normal = _normalize(np.cross(b - a, c - a))
    if normal[1] > 0:
        normal = -normal
    offset = -float(np.dot(normal, a))
    return normal, offset


def plane_angle_deg(a: GroundPlaneEstimate, b: GroundPlaneEstimate) -> float:
    na = _normalize(np.asarray(a.normal, dtype=np.float64))
    nb = _normalize(np.asarray(b.normal, dtype=np.float64))
    cos_v = float(np.clip(abs(np.dot(na, nb)), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_v)))


def _intrinsics_for_depth(
    config: GroundPerceptionConfig,
    camera_info: Optional[dict],
    *,
    raw_width: int,
    raw_height: int,
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    fx = config.depth_fx
    fy = config.depth_fy
    cx = config.depth_cx
    cy = config.depth_cy

    if isinstance(camera_info, dict):
        k = camera_info.get("k") or camera_info.get("K")
        if isinstance(k, (list, tuple)) and len(k) >= 6:
            fx = float(k[0])
            fy = float(k[4])
            cx = float(k[2])
            cy = float(k[5])

    if raw_width > 0 and raw_height > 0 and (raw_width != width or raw_height != height):
        sx = width / float(raw_width)
        sy = height / float(raw_height)
        fx *= sx
        cx *= sx
        fy *= sy
        cy *= sy

    return fx, fy, cx, cy


def estimate_ground_plane(
    depth_meters: object,
    *,
    config: GroundPerceptionConfig,
    camera_info: Optional[dict] = None,
    raw_width: int = 0,
    raw_height: int = 0,
    max_depth_m: float = 5.0,
    max_samples: int = 1600,
    iterations: int = 24,
    inlier_threshold_m: float = 0.035,
    max_expected_angle_deg: float = 35.0,
    max_expected_offset_delta_m: float = 0.80,
) -> GroundPlaneEstimate:
    """Fit the dominant lower-image plane from a depth image using RANSAC."""

    depth = np.asarray(depth_meters)
    if depth.ndim != 2 or depth.size == 0:
        return GroundPlaneEstimate((0.0, -1.0, 0.0), 0.0, 0.0, 0, 0, 0.0, False, "no depth")

    height, width = depth.shape
    raw_width = raw_width or width
    raw_height = raw_height or height
    fx, fy, cx, cy = _intrinsics_for_depth(
        config,
        camera_info,
        raw_width=raw_width,
        raw_height=raw_height,
        width=width,
        height=height,
    )
    if min(fx, fy) <= 1e-6:
        return GroundPlaneEstimate((0.0, -1.0, 0.0), 0.0, 0.0, 0, 0, 0.0, False, "bad intrinsics")

    v0 = int(height * 0.42)
    valid = np.isfinite(depth) & (depth >= 0.2) & (depth <= max_depth_m)
    valid[:v0, :] = False
    ys, xs = np.nonzero(valid)
    if xs.size < 80:
        return GroundPlaneEstimate((0.0, -1.0, 0.0), 0.0, 0.0, int(xs.size), 0, 0.0, False, "few points")

    if xs.size > max_samples:
        step = max(1, int(np.ceil(xs.size / float(max_samples))))
        xs = xs[::step]
        ys = ys[::step]

    z = depth[ys, xs].astype(np.float64)
    x = (xs.astype(np.float64) - cx) * z / fx
    y = (ys.astype(np.float64) - cy) * z / fy
    points = np.column_stack((x, y, z))
    sample_count = int(points.shape[0])
    expected_normal, expected_offset = _expected_ground_plane(config)
    min_expected_cos = float(np.cos(np.radians(max_expected_angle_deg)))

    rng = np.random.default_rng(12345)
    best_mask = None
    best_count = 0
    for _ in range(iterations):
        idx = rng.choice(sample_count, size=3, replace=False)
        p0, p1, p2 = points[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = float(np.linalg.norm(normal))
        if norm < 1e-6:
            continue
        normal = normal / norm
        if normal[1] > 0:
            normal = -normal
        if float(abs(np.dot(normal, expected_normal))) < min_expected_cos:
            continue
        offset = -float(np.dot(normal, p0))
        dist = np.abs(points @ normal + offset)
        mask = dist < inlier_threshold_m
        count = int(mask.sum())
        if count > best_count:
            best_count = count
            best_mask = mask

    if best_mask is None or best_count < 80:
        return GroundPlaneEstimate((0.0, -1.0, 0.0), 0.0, 0.0, sample_count, best_count, 0.0, False, "no plane")

    inliers = points[best_mask]
    centroid = inliers.mean(axis=0)
    _, _, vh = np.linalg.svd(inliers - centroid, full_matrices=False)
    normal = vh[-1]
    normal = normal / max(float(np.linalg.norm(normal)), 1e-9)
    # In optical coordinates y points down; floor normal should broadly point upward.
    if normal[1] > 0:
        normal = -normal
    if float(abs(np.dot(normal, expected_normal))) < min_expected_cos:
        return GroundPlaneEstimate((float(normal[0]), float(normal[1]), float(normal[2])), 0.0, 0.0, sample_count, best_count, 0.0, False, "bad normal")
    offset = -float(np.dot(normal, centroid))
    if abs(offset - expected_offset) > max_expected_offset_delta_m:
        return GroundPlaneEstimate(
            (float(normal[0]), float(normal[1]), float(normal[2])),
            offset,
            0.0,
            sample_count,
            best_count,
            0.0,
            False,
            "bad height",
        )
    residuals = inliers @ normal + offset
    rms = float(np.sqrt(np.mean(residuals * residuals)))
    ratio = best_count / float(sample_count)
    valid_estimate = ratio >= 0.18 and rms <= 0.055
    reason = "" if valid_estimate else "low confidence"
    return GroundPlaneEstimate(
        normal=(float(normal[0]), float(normal[1]), float(normal[2])),
        offset=offset,
        inlier_ratio=ratio,
        sample_count=sample_count,
        inlier_count=best_count,
        rms_error_m=rms,
        valid=valid_estimate,
        reason=reason,
    )
