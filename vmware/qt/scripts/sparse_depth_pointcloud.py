#!/usr/bin/env python3
"""Publish a strided depth point cloud on the VM (ROS1 Melodic)."""

import os
import struct

import rospy
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import CameraInfo, Image, PointCloud2

try:
    import numpy as np
except ImportError:
    np = None


def _cfg_int(key, default):
    try:
        return max(1, int(os.environ.get(key, str(default))))
    except (TypeError, ValueError):
        return default


def _cfg_float(key, default):
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


class SparseDepthPointCloud(object):
    def __init__(self):
        self.stride = _cfg_int("CAMERA_POINTCLOUD_STRIDE", 12)
        self.min_m = _cfg_float("CAMERA_POINTCLOUD_MIN_RANGE_M", 0.25)
        self.max_m = _cfg_float("CAMERA_POINTCLOUD_MAX_RANGE_M", 3.0)
        out_topic = os.environ.get(
            "VMWARE_DEPTH_POINTS_TOPIC", "/vmware/depth/points"
        )
        self.pub = rospy.Publisher(out_topic, PointCloud2, queue_size=2)
        self.info = None
        rospy.Subscriber(
            "/camera/depth/camera_info", CameraInfo, self._on_info, queue_size=1
        )
        rospy.Subscriber(
            "/camera/depth/image_raw", Image, self._on_image, queue_size=1
        )
        rospy.loginfo(
            "sparse_depth_pointcloud stride=%d range=%.2f..%.2fm -> %s",
            self.stride,
            self.min_m,
            self.max_m,
            out_topic,
        )

    def _on_info(self, msg):
        self.info = msg

    def _decode_depth_m(self, img):
        width = img.width
        height = img.height
        enc = img.encoding
        if np is not None:
            if enc in ("16UC1", "mono16"):
                depth = np.frombuffer(img.data, dtype=np.uint16).reshape(
                    height, width
                )
                depth_m = depth.astype(np.float32) * 0.001
            elif enc == "32FC1":
                depth_m = np.frombuffer(img.data, dtype=np.float32).reshape(
                    height, width
                )
            else:
                return None
            return depth_m

        points = []
        for v in range(height):
            for u in range(width):
                z = self._depth_scalar(img.data, enc, u, v, width)
                points.append(z)
        return points

    @staticmethod
    def _depth_scalar(data, encoding, u, v, width):
        idx = v * width + u
        if encoding in ("16UC1", "mono16"):
            raw = struct.unpack_from("<H", data, idx * 2)[0]
            if raw == 0:
                return float("nan")
            return raw * 0.001
        if encoding == "32FC1":
            return struct.unpack_from("<f", data, idx * 4)[0]
        return float("nan")

    def _on_image(self, img):
        if self.info is None:
            return

        fx = self.info.K[0]
        fy = self.info.K[4]
        cx = self.info.K[2]
        cy = self.info.K[5]
        if fx <= 1e-6 or fy <= 1e-6:
            return

        stride = self.stride
        frame_id = self.info.header.frame_id or img.header.frame_id
        points = []

        if np is not None:
            depth_m = self._decode_depth_m(img)
            if depth_m is None:
                return
            sampled = depth_m[::stride, ::stride]
            height, width = sampled.shape
            us = np.arange(0, img.width, stride, dtype=np.float32)
            vs = np.arange(0, img.height, stride, dtype=np.float32)
            uu, vv = np.meshgrid(us, vs)
            z = sampled
            valid = (
                np.isfinite(z)
                & (z >= self.min_m)
                & (z <= self.max_m)
            )
            if not np.any(valid):
                return
            x = (uu - cx) * z / fx
            y = (vv - cy) * z / fy
            pts = np.stack([x[valid], y[valid], z[valid]], axis=-1)
            points = [tuple(row) for row in pts.tolist()]
        else:
            for v in range(0, img.height, stride):
                for u in range(0, img.width, stride):
                    z = self._depth_scalar(img.data, img.encoding, u, v, img.width)
                    if z != z or z < self.min_m or z > self.max_m:
                        continue
                    x = (u - cx) * z / fx
                    y = (v - cy) * z / fy
                    points.append((x, y, z))

        if not points:
            return

        header = img.header
        header.frame_id = frame_id
        self.pub.publish(pc2.create_cloud_xyz32(header, points))


def main():
    rospy.init_node("vmware_depth_points", anonymous=False)
    SparseDepthPointCloud()
    rospy.spin()


if __name__ == "__main__":
    main()
