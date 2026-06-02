from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Bool, Float32MultiArray, String
from tf2_ros import Buffer, TransformException, TransformListener

try:
    from sensor_msgs_py.point_cloud2 import read_points_numpy
except ImportError:  # pragma: no cover - depends on ROS distro patch level.
    read_points_numpy = None

try:
    from tf2_sensor_msgs.tf2_sensor_msgs import do_transform_cloud
except ImportError:  # pragma: no cover - caught at runtime with a clear log.
    try:
        from tf2_sensor_msgs import do_transform_cloud
    except ImportError:
        do_transform_cloud = None


@dataclass
class StairCandidate:
    height: float
    distance: float
    width: float
    confidence: float
    point_count: int


class StairDetector(Node):
    """Detect climbable stair-like height discontinuities in a front LiDAR ROI."""

    def __init__(self) -> None:
        super().__init__("stair_detector")

        self._declare_parameters()
        self._load_parameters()

        self._confirmed_frames = 0
        self._clear_frames = 0
        self._is_detected = False
        self._last_trigger_time = self.get_clock().now()
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        self._cloud_sub = self.create_subscription(
            PointCloud2,
            self.cloud_topic,
            self._on_cloud,
            10,
        )
        self._detected_pub = self.create_publisher(Bool, self.stair_detected_topic, 10)
        self._info_pub = self.create_publisher(Float32MultiArray, self.stair_info_topic, 10)
        self._front_roi_pub = self.create_publisher(PointCloud2, self.front_roi_cloud_topic, 10)
        self._cmd_vel_pub = self.create_publisher(Twist, self.cmd_vel_topic, 10)
        self._trigger_pub = self.create_publisher(String, self.climb_trigger_topic, 10)

        self.get_logger().info(
            f"stair_detector listening on {self.cloud_topic}, ROI x=[{self.min_x}, {self.max_x}]m"
        )

    def _declare_parameters(self) -> None:
        defaults = {
            "cloud_topic": "/unilidar/cloud",
            "target_frame": "base_link",
            "stair_detected_topic": "/stair_detected",
            "stair_info_topic": "/stair_info",
            "front_roi_cloud_topic": "/front_roi_cloud",
            "cmd_vel_topic": "/cmd_vel",
            "climb_trigger_topic": "/climb_mode_trigger",
            "min_x": 0.30,
            "max_x": 2.00,
            "min_y": -0.80,
            "max_y": 0.80,
            "min_z": -0.35,
            "max_z": 0.80,
            "min_stair_height": 0.05,
            "max_stair_height": 0.25,
            "ground_threshold": 0.035,
            "distance_bin_size": 0.08,
            "min_points_per_bin": 8,
            "min_step_width": 0.35,
            "min_confidence": 0.55,
            "ransac_iterations": 40,
            "transform_timeout_sec": 0.05,
            "confirm_frames": 4,
            "clear_frames": 6,
            "enable_stop_command": False,
            "enable_climb_trigger": False,
            "trigger_cooldown_sec": 3.0,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_parameters(self) -> None:
        for name in (
            "cloud_topic",
            "target_frame",
            "stair_detected_topic",
            "stair_info_topic",
            "front_roi_cloud_topic",
            "cmd_vel_topic",
            "climb_trigger_topic",
        ):
            setattr(self, name, self.get_parameter(name).get_parameter_value().string_value)

        for name in (
            "min_x",
            "max_x",
            "min_y",
            "max_y",
            "min_z",
            "max_z",
            "min_stair_height",
            "max_stair_height",
            "ground_threshold",
            "distance_bin_size",
            "min_step_width",
            "min_confidence",
            "transform_timeout_sec",
            "trigger_cooldown_sec",
        ):
            setattr(self, name, self.get_parameter(name).get_parameter_value().double_value)

        for name in ("min_points_per_bin", "ransac_iterations", "confirm_frames", "clear_frames"):
            setattr(self, name, self.get_parameter(name).get_parameter_value().integer_value)

        for name in ("enable_stop_command", "enable_climb_trigger"):
            setattr(self, name, self.get_parameter(name).get_parameter_value().bool_value)

    def _on_cloud(self, msg: PointCloud2) -> None:
        transformed = self._transform_cloud(msg)
        if transformed is None:
            self._publish_detection(False, None)
            return

        points = self._read_xyz(transformed)
        if points.size == 0:
            self._publish_detection(False, None)
            return

        roi = self._filter_roi(points)
        self._publish_front_roi_cloud(transformed, roi)
        candidate = self._detect_stair(roi)
        detected = candidate is not None and candidate.confidence >= self.min_confidence
        stable_detected = self._update_temporal_filter(detected)

        self._publish_detection(stable_detected, candidate)
        if stable_detected and candidate is not None:
            self._maybe_trigger_climb(candidate)

    def _read_xyz(self, msg: PointCloud2) -> np.ndarray:
        if read_points_numpy is not None:
            points = read_points_numpy(msg, field_names=("x", "y", "z"), skip_nans=True)
            return np.asarray(points, dtype=np.float32).reshape((-1, 3))

        rows = point_cloud2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)
        points = np.array(list(rows), dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 3:
            return np.empty((0, 3), dtype=np.float32)
        return points

    def _transform_cloud(self, msg: PointCloud2) -> Optional[PointCloud2]:
        if not self.target_frame or msg.header.frame_id == self.target_frame:
            return msg
        if do_transform_cloud is None:
            self.get_logger().error("tf2_sensor_msgs is required to transform PointCloud2")
            return None
        try:
            transform = self._tf_buffer.lookup_transform(
                self.target_frame,
                msg.header.frame_id,
                msg.header.stamp,
                timeout=Duration(seconds=self.transform_timeout_sec),
            )
            return do_transform_cloud(msg, transform)
        except TransformException as exc:
            self.get_logger().warning(f"TF lookup failed: {exc}")
            return None

    def _filter_roi(self, points: np.ndarray) -> np.ndarray:
        mask = (
            (points[:, 0] >= self.min_x)
            & (points[:, 0] <= self.max_x)
            & (points[:, 1] >= self.min_y)
            & (points[:, 1] <= self.max_y)
            & (points[:, 2] >= self.min_z)
            & (points[:, 2] <= self.max_z)
        )
        return points[mask]

    def _detect_stair(self, roi: np.ndarray) -> Optional[StairCandidate]:
        if roi.shape[0] < self.min_points_per_bin * 3:
            return None

        ground_plane = self._estimate_ground_plane(roi)
        if ground_plane is None:
            return None

        ground_heights = self._height_above_plane(roi, ground_plane)
        above_ground = roi[ground_heights > self.min_stair_height * 0.5]
        if above_ground.shape[0] < self.min_points_per_bin:
            return None

        bins = np.arange(self.min_x, self.max_x + self.distance_bin_size, self.distance_bin_size)
        if bins.size < 3:
            return None

        best: Optional[StairCandidate] = None
        for left, right in zip(bins[:-1], bins[1:]):
            band = roi[(roi[:, 0] >= left) & (roi[:, 0] < right)]
            if band.shape[0] < self.min_points_per_bin:
                continue

            band_heights = self._height_above_plane(band, ground_plane)
            upper = band[band_heights > self.min_stair_height * 0.5]
            upper_heights = band_heights[band_heights > self.min_stair_height * 0.5]
            if upper.shape[0] < self.min_points_per_bin:
                continue

            height = float(np.percentile(upper_heights, 60))
            if height < self.min_stair_height or height > self.max_stair_height:
                continue

            width = float(np.percentile(upper[:, 1], 95) - np.percentile(upper[:, 1], 5))
            if width < self.min_step_width:
                continue

            vertical_density = self._vertical_edge_score(band, band_heights, height)
            width_score = min(width / max(self.min_step_width, 1e-3), 1.0)
            height_score = 1.0 - min(
                abs(height - (self.min_stair_height + self.max_stair_height) * 0.5)
                / max(self.max_stair_height - self.min_stair_height, 1e-3),
                1.0,
            )
            count_score = min(upper.shape[0] / max(self.min_points_per_bin * 4, 1), 1.0)
            confidence = float(
                0.35 * vertical_density
                + 0.25 * width_score
                + 0.20 * height_score
                + 0.20 * count_score
            )

            candidate = StairCandidate(
                height=height,
                distance=float((left + right) * 0.5),
                width=width,
                confidence=confidence,
                point_count=int(upper.shape[0]),
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate

        return best

    def _estimate_ground_plane(self, roi: np.ndarray) -> Optional[np.ndarray]:
        candidates = roi[roi[:, 2] <= np.percentile(roi[:, 2], 45)]
        if candidates.shape[0] < 3:
            return None

        best_plane = None
        best_inliers = 0
        rng = np.random.default_rng(7)
        for _ in range(self.ransac_iterations):
            sample = candidates[rng.choice(candidates.shape[0], size=3, replace=False)]
            normal = np.cross(sample[1] - sample[0], sample[2] - sample[0])
            norm = np.linalg.norm(normal)
            if norm < 1e-6:
                continue
            normal = normal / norm
            if normal[2] < 0.0:
                normal = -normal
            if normal[2] < 0.65:
                continue
            d = -float(np.dot(normal, sample[0]))
            distances = np.abs(candidates @ normal + d)
            inliers = int(np.count_nonzero(distances < self.ground_threshold))
            if inliers > best_inliers:
                best_inliers = inliers
                best_plane = np.array([normal[0], normal[1], normal[2], d], dtype=np.float32)

        if best_plane is None:
            z = float(np.percentile(roi[:, 2], 10))
            best_plane = np.array([0.0, 0.0, 1.0, -z], dtype=np.float32)
        return best_plane

    def _height_above_plane(self, points: np.ndarray, plane: np.ndarray) -> np.ndarray:
        normal = plane[:3]
        d = plane[3]
        return points @ normal + d

    def _vertical_edge_score(self, band: np.ndarray, heights: np.ndarray, height: float) -> float:
        lower = np.count_nonzero(np.abs(heights) <= self.ground_threshold)
        mid_mask = (heights > self.ground_threshold) & (heights < height - self.ground_threshold)
        upper_mask = heights >= height - self.ground_threshold
        mid = np.count_nonzero(mid_mask)
        upper = np.count_nonzero(upper_mask)
        if lower + upper + mid == 0:
            return 0.0

        if np.count_nonzero(mid_mask | upper_mask) >= self.min_points_per_bin:
            elevated = band[mid_mask | upper_mask]
            x_span = float(np.percentile(elevated[:, 0], 90) - np.percentile(elevated[:, 0], 10))
        else:
            x_span = self.distance_bin_size

        vertical_fill = mid / max(lower + mid + upper, 1)
        riser_score = 1.0 - min(x_span / max(self.distance_bin_size * 2.0, 1e-3), 1.0)
        tread_score = upper / max(self.min_points_per_bin * 3, 1)
        return float(min(0.45 * vertical_fill + 0.35 * riser_score + 0.20 * tread_score, 1.0))

    def _update_temporal_filter(self, detected: bool) -> bool:
        if detected:
            self._confirmed_frames += 1
            self._confirmed_frames = min(self._confirmed_frames, self.confirm_frames + 1)
            self._clear_frames = 0
        else:
            self._clear_frames += 1
            if self._clear_frames >= self.clear_frames:
                self._confirmed_frames = 0
                self._is_detected = False

        if self._confirmed_frames >= self.confirm_frames:
            self._is_detected = True
        return self._is_detected

    def _publish_detection(self, detected: bool, candidate: Optional[StairCandidate]) -> None:
        self._detected_pub.publish(Bool(data=detected))
        info = Float32MultiArray()
        if not detected or candidate is None:
            info.data = [1.0 if detected else 0.0, 0.0, 0.0, 0.0, 0.0]
        else:
            info.data = [
                1.0 if detected else 0.0,
                candidate.height,
                candidate.distance,
                candidate.width,
                candidate.confidence,
            ]
        self._info_pub.publish(info)

    def _publish_front_roi_cloud(self, source: PointCloud2, roi: np.ndarray) -> None:
        if roi.size == 0:
            return
        cloud = point_cloud2.create_cloud_xyz32(source.header, roi.tolist())
        self._front_roi_pub.publish(cloud)

    def _maybe_trigger_climb(self, candidate: StairCandidate) -> None:
        if self.enable_stop_command:
            self._cmd_vel_pub.publish(Twist())

        if not self.enable_climb_trigger:
            return

        now = self.get_clock().now()
        elapsed = (now - self._last_trigger_time).nanoseconds / 1e9
        if elapsed < self.trigger_cooldown_sec:
            return

        msg = String()
        msg.data = (
            f"climb_requested height={candidate.height:.3f} "
            f"distance={candidate.distance:.3f} confidence={candidate.confidence:.2f}"
        )
        self._trigger_pub.publish(msg)
        self._last_trigger_time = now
        self.get_logger().warning(msg.data)


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = StairDetector()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
