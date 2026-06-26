#!/usr/bin/env python
"""16UC1 depth -> pseudo-color rgb8 for web_video_server / Qt MJPEG preview."""

from __future__ import division

import numpy as np
import rospy
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image

try:
    import cv2
except ImportError:
    cv2 = None


class DepthPreviewNode(object):
  def __init__(self):
    self._input = rospy.get_param("~input_topic", "/camera/depth/image_raw")
    self._output = rospy.get_param("~output_topic", "/camera/depth/preview")
    self._max_mm = float(rospy.get_param("~max_range_mm", 4000))
    self._skip = max(1, int(rospy.get_param("~frame_skip", 2)))
    self._count = 0
    self._bridge = CvBridge()
    self._pub = rospy.Publisher(self._output, Image, queue_size=1)
    self._sub = rospy.Subscriber(
      self._input, Image, self._on_depth, queue_size=1, buff_size=2**20
    )
    rospy.loginfo(
      "depth preview %s -> %s (max_range_mm=%.0f)",
      self._input,
      self._output,
      self._max_mm,
    )

  def _on_depth(self, msg):
    self._count += 1
    if self._count % self._skip != 0:
      return
    try:
      depth = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
    except CvBridgeError as exc:
      rospy.logwarn_throttle(5.0, "cv_bridge failed: %s", exc)
      return

    if depth.dtype != np.uint16:
      depth = depth.astype(np.uint16)

    valid = depth > 0
    vis = np.zeros(depth.shape, dtype=np.uint8)
    if valid.any():
      clipped = np.clip(depth.astype(np.float32), 0.0, self._max_mm)
      norm = (clipped / max(self._max_mm, 1.0) * 255.0).astype(np.uint8)
      vis[valid] = norm[valid]

    if cv2 is not None:
      color = cv2.applyColorMap(vis, cv2.COLORMAP_JET)
      color[~valid] = (0, 0, 0)
      try:
        out = self._bridge.cv2_to_imgmsg(color, encoding="bgr8")
      except CvBridgeError as exc:
        rospy.logwarn_throttle(5.0, "publish encode failed: %s", exc)
        return
    else:
      try:
        out = self._bridge.cv2_to_imgmsg(vis, encoding="mono8")
      except CvBridgeError as exc:
        rospy.logwarn_throttle(5.0, "publish encode failed: %s", exc)
        return

    out.header = msg.header
    self._pub.publish(out)


def main():
  rospy.init_node("depth_preview")
  DepthPreviewNode()
  rospy.spin()


if __name__ == "__main__":
  main()
