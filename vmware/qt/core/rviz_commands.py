"""Build shell command to start local RViz on VMware VM."""

import shlex

from core.env import bash_ros_prefix


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
