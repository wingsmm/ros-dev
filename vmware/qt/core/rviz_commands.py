"""Build shell command to start local RViz on VMware VM."""

import shlex

from core.env import (
    DEPTH_PREVIEW_TOPIC,
    VMWARE_DEPTH_POINTS_TOPIC,
    bash_ros_prefix,
)
IMAGE_VIEW_MODES = ("深度轻量", "RGB+Depth 诊断", "深度增强")

# Extra preview image_view + VM-side depth point cloud (深度增强 only).
DEPTH_ENHANCED_MODE = "深度增强"


class RvizCommands(object):
    def __init__(self, cfg):
        self.cfg = cfg

    def start_command(self, rviz_config):
        path = shlex.quote(str(rviz_config.resolve()))
        return "%srviz -d %s" % (bash_ros_prefix(self.cfg), path)

    def depth_image_view_command(self):
        return (
            "%srosrun image_view image_view image:=/camera/depth/image_raw "
            "__name:=vmware_depth_view"
            % bash_ros_prefix(self.cfg)
        )

    def rgb_image_view_command(self):
        return (
            "%srosrun image_view image_view image:=/camera/image_raw "
            "__name:=vmware_rgb_view"
            % bash_ros_prefix(self.cfg)
        )

    def preview_image_view_command(self):
        return (
            "%srosrun image_view image_view image:=%s "
            "__name:=vmware_depth_preview_view"
            % (bash_ros_prefix(self.cfg), DEPTH_PREVIEW_TOPIC)
        )

    def depth_point_cloud_command(self):
        c = self.cfg
        script = shlex.quote(str(c.app_dir / "scripts" / "sparse_depth_pointcloud.py"))
        return (
            "%s"
            "export CAMERA_POINTCLOUD_STRIDE=%d "
            "CAMERA_POINTCLOUD_MIN_RANGE_M=%s CAMERA_POINTCLOUD_MAX_RANGE_M=%s "
            "VMWARE_DEPTH_POINTS_TOPIC=%s; "
            "python2 %s"
            % (
                bash_ros_prefix(self.cfg),
                c.camera_pointcloud_stride,
                c.camera_pointcloud_min_range_m,
                c.camera_pointcloud_max_range_m,
                VMWARE_DEPTH_POINTS_TOPIC,
                script,
            )
        )

    def camera_base_tf_command(self):
        c = self.cfg
        return (
            "%srosrun tf static_transform_publisher "
            "%s %s %s %s %s %s "
            "%s %s 100 "
            "__name:=vmware_camera_base_tf"
            % (
                bash_ros_prefix(self.cfg),
                c.camera_x,
                c.camera_y,
                c.camera_z,
                c.camera_yaw,
                c.camera_pitch,
                c.camera_roll,
                c.robot_base_frame,
                c.camera_frame,
            )
        )

    def camera_optical_tf_command(self):
        c = self.cfg
        # ROS1 static_transform_publisher: x y z yaw pitch roll parent child period_ms
        return (
            "%srosrun tf static_transform_publisher "
            "0 0 0 -1.57079632679 0 -1.57079632679 "
            "%s %s 100 "
            "__name:=vmware_camera_optical_tf"
            % (
                bash_ros_prefix(self.cfg),
                c.camera_frame,
                c.camera_optical_frame,
            )
        )
