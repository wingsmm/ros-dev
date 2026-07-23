#!/usr/bin/env python2
"""Collect replay statistics for Stage B isolated bag playback."""

from __future__ import print_function

import json
import os
import sys
import threading
import time

import rospy
from sensor_msgs.msg import CameraInfo, Image, PointCloud2
from std_msgs.msg import String


class ReplayProbe(object):
    def __init__(self, report_path):
        self.report_path = report_path
        self.lock = threading.Lock()
        self.depth_count = 0
        self.info_count = 0
        self.cloud_count = 0
        self.first_stamp = None
        self.last_stamp = None
        self.cloud_frame = ""
        self.filter_stats = {}
        self.guard_alive = False
        self.guard_conflict = False
        self.started_wall = time.time()

        rospy.Subscriber(
            "/camera/depth/image_raw", Image, self._on_depth, queue_size=50
        )
        rospy.Subscriber(
            "/camera/depth/camera_info", CameraInfo, self._on_info, queue_size=50
        )
        rospy.Subscriber(
            "/vmware/depth/points", PointCloud2, self._on_cloud, queue_size=50
        )
        rospy.Subscriber(
            "/astra_tf_edge_filter/stats",
            String,
            self._on_filter_stats,
            queue_size=10,
        )

    def _touch_stamp(self, stamp):
        if stamp is None:
            return
        sec = stamp.to_sec()
        if sec <= 0.0:
            return
        if self.first_stamp is None or sec < self.first_stamp:
            self.first_stamp = sec
        if self.last_stamp is None or sec > self.last_stamp:
            self.last_stamp = sec

    def _on_depth(self, msg):
        with self.lock:
            self.depth_count += 1
            self._touch_stamp(msg.header.stamp)

    def _on_info(self, msg):
        with self.lock:
            self.info_count += 1
            self._touch_stamp(msg.header.stamp)

    def _on_cloud(self, msg):
        with self.lock:
            self.cloud_count += 1
            self.cloud_frame = str(msg.header.frame_id or "")
            self._touch_stamp(msg.header.stamp)

    def _on_filter_stats(self, msg):
        try:
            payload = json.loads(msg.data)
        except ValueError:
            return
        with self.lock:
            self.filter_stats = payload

    def snapshot(self):
        with self.lock:
            duration = 0.0
            if self.first_stamp is not None and self.last_stamp is not None:
                duration = max(0.0, self.last_stamp - self.first_stamp)
            try:
                import rosnode

                nodes = set(rosnode.get_node_names())
                self.guard_alive = "/astra_camera_tf_guard" in nodes
            except Exception:
                pass
            return {
                "depth_frame_count": self.depth_count,
                "camera_info_count": self.info_count,
                "point_cloud_count": self.cloud_count,
                "first_stamp_s": self.first_stamp,
                "last_stamp_s": self.last_stamp,
                "simulated_duration_s": duration,
                "point_cloud_frame": self.cloud_frame,
                "tf_filter_stats": dict(self.filter_stats),
                "tf_filter_dropped": int(self.filter_stats.get("dropped", 0)),
                "tf_guard_alive": self.guard_alive,
                "tf_guard_conflict": self.guard_conflict,
                "wall_elapsed_s": time.time() - self.started_wall,
                "ROS_MASTER_URI": os.environ.get("ROS_MASTER_URI", ""),
            }

    def write_report(self):
        payload = self.snapshot()
        directory = os.path.dirname(self.report_path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(self.report_path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return payload


def main():
    rospy.init_node("astra_replay_probe")
    report_path = rospy.get_param(
        "~report_path",
        os.environ.get(
            "ASTRA_REPLAY_REPORT",
            "/tmp/astra_replay_probe.json",
        ),
    )
    probe = ReplayProbe(report_path)
    rospy.loginfo("replay_probe writing reports to %s", report_path)

    def _on_shutdown():
        payload = probe.write_report()
        rospy.loginfo(
            "probe final depth=%s info=%s cloud=%s dropped=%s",
            payload["depth_frame_count"],
            payload["camera_info_count"],
            payload["point_cloud_count"],
            payload["tf_filter_dropped"],
        )

    rospy.on_shutdown(_on_shutdown)
    rate = rospy.Rate(1.0)
    while not rospy.is_shutdown():
        probe.write_report()
        rate.sleep()
    return 0


if __name__ == "__main__":
    sys.exit(main())
