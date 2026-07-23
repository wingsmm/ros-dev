#!/usr/bin/env python2
"""Publish a strided depth point cloud on the VM (ROS1 Melodic)."""

import os
import struct

import rospy
import sensor_msgs.point_cloud2 as pc2
from sensor_msgs.msg import CameraInfo, Image, PointCloud2
from std_msgs.msg import Header

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
        # Astra often latches CameraInfo with a stale stamp; default is warn-only
        # unless CAMERA_INFO_MAX_AGE_S is set > 0 as a hard reject threshold.
        self.max_info_age_s = max(
            0.0, _cfg_float("CAMERA_INFO_MAX_AGE_S", 0.0)
        )
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

    @staticmethod
    def _encoding_layout(encoding):
        if encoding in ("16UC1", "mono16"):
            return "u2", 2, 0.001
        if encoding == "32FC1":
            return "f4", 4, 1.0
        return None

    def _validate_image_layout(self, img):
        layout = self._encoding_layout(img.encoding)
        if layout is None:
            rospy.logwarn_throttle(
                5.0, "Unsupported depth encoding: %s" % img.encoding
            )
            return None
        _, bytes_per_pixel, _ = layout
        minimum_step = img.width * bytes_per_pixel
        if img.step < minimum_step:
            rospy.logwarn_throttle(
                5.0,
                "Invalid depth step=%d, expected at least %d"
                % (img.step, minimum_step),
            )
            return None
        required_size = img.step * img.height
        if len(img.data) < required_size:
            rospy.logwarn_throttle(
                5.0,
                "Truncated depth buffer=%d, expected at least %d"
                % (len(img.data), required_size),
            )
            return None
        return layout

    def _decode_depth_m(self, img):
        layout = self._validate_image_layout(img)
        if layout is None or np is None:
            return None
        dtype_code, bytes_per_pixel, scale = layout
        byte_order = ">" if img.is_bigendian else "<"
        depth = np.ndarray(
            shape=(img.height, img.width),
            dtype=np.dtype(byte_order + dtype_code),
            buffer=img.data,
            strides=(img.step, bytes_per_pixel),
        )
        return depth.astype(np.float32) * scale

    @classmethod
    def _depth_scalar(cls, img, u, v):
        layout = cls._encoding_layout(img.encoding)
        if layout is None:
            return float("nan")
        _, bytes_per_pixel, scale = layout
        offset = v * img.step + u * bytes_per_pixel
        byte_order = ">" if img.is_bigendian else "<"
        if img.encoding in ("16UC1", "mono16"):
            raw = struct.unpack_from(byte_order + "H", img.data, offset)[0]
            if raw == 0:
                return float("nan")
            return raw * scale
        if img.encoding == "32FC1":
            return struct.unpack_from(byte_order + "f", img.data, offset)[0]
        return float("nan")

    def _on_image(self, img):
        if self.info is None:
            rospy.logwarn_throttle(5.0, "Waiting for depth CameraInfo")
            return

        if self._validate_image_layout(img) is None:
            return
        if self.info.width and self.info.width != img.width:
            rospy.logwarn_throttle(
                5.0,
                "CameraInfo width=%d does not match depth width=%d"
                % (self.info.width, img.width),
            )
            return
        if self.info.height and self.info.height != img.height:
            rospy.logwarn_throttle(
                5.0,
                "CameraInfo height=%d does not match depth height=%d"
                % (self.info.height, img.height),
            )
            return
        image_frame = img.header.frame_id
        info_frame = self.info.header.frame_id
        if not image_frame:
            rospy.logwarn_throttle(5.0, "Depth image frame_id is empty")
            return
        if info_frame and info_frame.lstrip("/") != image_frame.lstrip("/"):
            rospy.logwarn_throttle(
                5.0,
                "CameraInfo frame=%s does not match depth frame=%s"
                % (info_frame, image_frame),
            )
            return
        image_stamp = img.header.stamp.to_sec()
        info_stamp = self.info.header.stamp.to_sec()
        if image_stamp > 0.0 and info_stamp > 0.0:
            age = abs(image_stamp - info_stamp)
            if age > 1.0:
                rospy.logwarn_throttle(
                    5.0,
                    "CameraInfo timestamp differs from depth by %.3fs"
                    % age,
                )
            if self.max_info_age_s > 0.0 and age > self.max_info_age_s:
                return

        fx = self.info.K[0]
        fy = self.info.K[4]
        cx = self.info.K[2]
        cy = self.info.K[5]
        if fx <= 1e-6 or fy <= 1e-6:
            return

        stride = self.stride
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
                    z = self._depth_scalar(img, u, v)
                    if z != z or z < self.min_m or z > self.max_m:
                        continue
                    x = (u - cx) * z / fx
                    y = (v - cy) * z / fy
                    points.append((x, y, z))

        if not points:
            return

        header = Header(
            seq=img.header.seq,
            stamp=img.header.stamp,
            frame_id=image_frame,
        )
        self.pub.publish(pc2.create_cloud_xyz32(header, points))


def main():
    rospy.init_node("vmware_depth_points", anonymous=False)
    SparseDepthPointCloud()
    rospy.spin()


if __name__ == "__main__":
    main()
