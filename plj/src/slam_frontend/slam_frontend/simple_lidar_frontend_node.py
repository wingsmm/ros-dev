from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header
from tf2_ros import TransformBroadcaster

try:
    from sensor_msgs_py.point_cloud2 import read_points_numpy
except ImportError:  # pragma: no cover - depends on ROS patch level.
    read_points_numpy = None


@dataclass
class Pose2D:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0


class SimpleLidarFrontend(Node):
    """Small self-contained LiDAR odometry frontend for project validation.

    The node intentionally avoids Point-LIO/FAST-LIO dependencies. It estimates
    frame-to-frame planar motion from point clouds with a lightweight ICP loop.
    Use it to validate wiring, TF, timing, and downstream perception; it is not a
    replacement for a production tightly-coupled LiDAR-IMU odometry system.
    """

    def __init__(self) -> None:
        super().__init__("simple_lidar_frontend")
        self._declare_parameters()
        self._load_parameters()

        self.prev_xy: Optional[np.ndarray] = None
        self.pose = Pose2D()
        self.path = Path()
        self.path.header.frame_id = self.odom_frame
        self.keyframes: list[np.ndarray] = []
        self.last_keyframe_pose = Pose2D()

        self.tf_broadcaster = TransformBroadcaster(self)
        self.create_subscription(PointCloud2, self.cloud_topic, self._on_cloud, 10)
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, 10)
        self.path_pub = self.create_publisher(Path, self.path_topic, 10)
        self.local_map_pub = self.create_publisher(PointCloud2, self.local_map_topic, 2)

        self.get_logger().info(
            f"simple_lidar_frontend listening on {self.cloud_topic}; "
            f"publishing {self.odom_frame}->{self.base_frame}"
        )

    def _declare_parameters(self) -> None:
        defaults = {
            "cloud_topic": "/unilidar/cloud",
            "odom_topic": "/frontend/odom",
            "path_topic": "/frontend/path",
            "local_map_topic": "/frontend/local_map",
            "odom_frame": "odom",
            "base_frame": "base_link",
            "publish_tf": True,
            "voxel_size": 0.18,
            "min_range": 0.30,
            "max_range": 8.00,
            "max_points": 700,
            "icp_iterations": 8,
            "max_correspondence_distance": 0.65,
            "min_correspondences": 45,
            "keyframe_translation": 0.20,
            "keyframe_yaw": 0.12,
            "local_map_keyframes": 20,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _load_parameters(self) -> None:
        for name in (
            "cloud_topic",
            "odom_topic",
            "path_topic",
            "local_map_topic",
            "odom_frame",
            "base_frame",
        ):
            setattr(self, name, self.get_parameter(name).get_parameter_value().string_value)
        for name in (
            "voxel_size",
            "min_range",
            "max_range",
            "max_correspondence_distance",
            "keyframe_translation",
            "keyframe_yaw",
        ):
            setattr(self, name, self.get_parameter(name).get_parameter_value().double_value)
        for name in ("max_points", "icp_iterations", "min_correspondences", "local_map_keyframes"):
            setattr(self, name, self.get_parameter(name).get_parameter_value().integer_value)
        self.publish_tf = self.get_parameter("publish_tf").get_parameter_value().bool_value

    def _on_cloud(self, msg: PointCloud2) -> None:
        points = self._read_xyz(msg)
        if points.shape[0] < self.min_correspondences:
            self.get_logger().warning("not enough points for frontend update")
            return

        points = self._prepare_points(points)
        if points.shape[0] < self.min_correspondences:
            self.get_logger().warning("not enough filtered points for frontend update")
            return

        xy = points[:, :2]
        if self.prev_xy is None:
            self.prev_xy = xy
            self._add_keyframe(points)
            self._publish(msg.header, points)
            return

        alignment = self._align_current_to_previous(xy, self.prev_xy)
        if alignment is not None:
            dx, dy, dyaw, correspondences = alignment
            self._integrate_motion(dx, dy, dyaw)
            if correspondences < self.min_correspondences * 2:
                self.get_logger().warning(f"weak ICP update: {correspondences} correspondences")
        else:
            self.get_logger().warning("ICP update rejected; holding previous pose")

        self.prev_xy = xy
        if self._should_add_keyframe():
            self._add_keyframe(points)
        self._publish(msg.header, points)

    def _read_xyz(self, msg: PointCloud2) -> np.ndarray:
        if read_points_numpy is not None:
            points = read_points_numpy(msg, field_names=("x", "y", "z"), skip_nans=True)
            return np.asarray(points, dtype=np.float32).reshape((-1, 3))
        rows = point_cloud2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)
        points = np.array(list(rows), dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 3:
            return np.empty((0, 3), dtype=np.float32)
        return points

    def _prepare_points(self, points: np.ndarray) -> np.ndarray:
        ranges = np.linalg.norm(points[:, :2], axis=1)
        mask = (ranges >= self.min_range) & (ranges <= self.max_range)
        filtered = points[mask]
        if filtered.shape[0] == 0:
            return filtered

        keys = np.floor(filtered / self.voxel_size).astype(np.int32)
        _, unique_idx = np.unique(keys, axis=0, return_index=True)
        sampled = filtered[np.sort(unique_idx)]
        if sampled.shape[0] > self.max_points:
            idx = np.linspace(0, sampled.shape[0] - 1, self.max_points).astype(np.int32)
            sampled = sampled[idx]
        return sampled.astype(np.float32, copy=False)

    def _align_current_to_previous(
        self,
        current_xy: np.ndarray,
        previous_xy: np.ndarray,
    ) -> Optional[tuple[float, float, float, int]]:
        yaw = 0.0
        translation = np.zeros(2, dtype=np.float32)
        max_dist2 = self.max_correspondence_distance * self.max_correspondence_distance
        correspondences = 0

        for _ in range(self.icp_iterations):
            transformed = self._transform_xy(current_xy, translation, yaw)
            src, dst = self._nearest_pairs(transformed, previous_xy, max_dist2)
            correspondences = src.shape[0]
            if correspondences < self.min_correspondences:
                return None
            delta_t, delta_yaw = self._best_fit_transform(src, dst)
            transformed_translation = self._rotate(delta_t, yaw)
            translation = translation + transformed_translation
            yaw = self._normalize_angle(yaw + delta_yaw)

        # alignment maps current -> previous, so invert it to get previous -> current motion.
        motion_yaw = -yaw
        motion_xy = -self._rotate(translation, motion_yaw)
        return float(motion_xy[0]), float(motion_xy[1]), float(motion_yaw), correspondences

    def _nearest_pairs(
        self,
        source: np.ndarray,
        target: np.ndarray,
        max_dist2: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        src_chunks = []
        dst_chunks = []
        chunk_size = 128
        for start in range(0, source.shape[0], chunk_size):
            chunk = source[start : start + chunk_size]
            diff = chunk[:, None, :] - target[None, :, :]
            dist2 = np.einsum("ijk,ijk->ij", diff, diff)
            nearest = np.argmin(dist2, axis=1)
            nearest_dist2 = dist2[np.arange(chunk.shape[0]), nearest]
            keep = nearest_dist2 <= max_dist2
            if np.any(keep):
                src_chunks.append(chunk[keep])
                dst_chunks.append(target[nearest[keep]])

        if not src_chunks:
            return np.empty((0, 2), dtype=np.float32), np.empty((0, 2), dtype=np.float32)
        return np.vstack(src_chunks), np.vstack(dst_chunks)

    def _best_fit_transform(self, source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, float]:
        src_mean = np.mean(source, axis=0)
        dst_mean = np.mean(target, axis=0)
        src_centered = source - src_mean
        dst_centered = target - dst_mean
        covariance = src_centered.T @ dst_centered
        u, _s, vt = np.linalg.svd(covariance)
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0.0:
            vt[-1, :] *= -1.0
            rotation = vt.T @ u.T
        yaw = math.atan2(rotation[1, 0], rotation[0, 0])
        translation = dst_mean - rotation @ src_mean
        return translation.astype(np.float32), yaw

    def _integrate_motion(self, dx: float, dy: float, dyaw: float) -> None:
        world_delta = self._rotate(np.array([dx, dy], dtype=np.float32), self.pose.yaw)
        self.pose.x += float(world_delta[0])
        self.pose.y += float(world_delta[1])
        self.pose.yaw = self._normalize_angle(self.pose.yaw + dyaw)

    def _should_add_keyframe(self) -> bool:
        distance = math.hypot(
            self.pose.x - self.last_keyframe_pose.x,
            self.pose.y - self.last_keyframe_pose.y,
        )
        yaw_delta = abs(self._normalize_angle(self.pose.yaw - self.last_keyframe_pose.yaw))
        return distance >= self.keyframe_translation or yaw_delta >= self.keyframe_yaw

    def _add_keyframe(self, points: np.ndarray) -> None:
        world_points = points.copy()
        translation = np.array([self.pose.x, self.pose.y], dtype=np.float32)
        world_points[:, :2] = self._transform_xy(world_points[:, :2], translation, self.pose.yaw)
        self.keyframes.append(world_points)
        self.keyframes = self.keyframes[-self.local_map_keyframes :]
        self.last_keyframe_pose = Pose2D(self.pose.x, self.pose.y, self.pose.yaw)

    def _publish(self, header: Header, current_points: np.ndarray) -> None:
        stamp = header.stamp
        self._publish_tf(stamp)
        self._publish_odom(stamp)
        self._publish_path(stamp)
        self._publish_local_map(stamp, current_points)

    def _publish_tf(self, stamp) -> None:
        if not self.publish_tf:
            return
        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = self.odom_frame
        transform.child_frame_id = self.base_frame
        transform.transform.translation.x = self.pose.x
        transform.transform.translation.y = self.pose.y
        transform.transform.rotation.z = math.sin(self.pose.yaw * 0.5)
        transform.transform.rotation.w = math.cos(self.pose.yaw * 0.5)
        self.tf_broadcaster.sendTransform(transform)

    def _publish_odom(self, stamp) -> None:
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        odom.pose.pose.position.x = self.pose.x
        odom.pose.pose.position.y = self.pose.y
        odom.pose.pose.orientation.z = math.sin(self.pose.yaw * 0.5)
        odom.pose.pose.orientation.w = math.cos(self.pose.yaw * 0.5)
        self.odom_pub.publish(odom)

    def _publish_path(self, stamp) -> None:
        pose = PoseStamped()
        pose.header.stamp = stamp
        pose.header.frame_id = self.odom_frame
        pose.pose.position.x = self.pose.x
        pose.pose.position.y = self.pose.y
        pose.pose.orientation.z = math.sin(self.pose.yaw * 0.5)
        pose.pose.orientation.w = math.cos(self.pose.yaw * 0.5)
        self.path.poses.append(pose)
        self.path.poses = self.path.poses[-500:]
        self.path.header.stamp = stamp
        self.path_pub.publish(self.path)

    def _publish_local_map(self, stamp, current_points: np.ndarray) -> None:
        if self.keyframes:
            points = np.vstack(self.keyframes)
        else:
            points = current_points
        header = Header()
        header.stamp = stamp
        header.frame_id = self.odom_frame
        cloud = point_cloud2.create_cloud_xyz32(header, points.tolist())
        self.local_map_pub.publish(cloud)

    @staticmethod
    def _transform_xy(points: np.ndarray, translation: np.ndarray, yaw: float) -> np.ndarray:
        c = math.cos(yaw)
        s = math.sin(yaw)
        rotation = np.array([[c, -s], [s, c]], dtype=np.float32)
        return points @ rotation.T + translation

    @staticmethod
    def _rotate(vector: np.ndarray, yaw: float) -> np.ndarray:
        c = math.cos(yaw)
        s = math.sin(yaw)
        return np.array([c * vector[0] - s * vector[1], s * vector[0] + c * vector[1]], dtype=np.float32)

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        return math.atan2(math.sin(angle), math.cos(angle))


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = SimpleLidarFrontend()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
