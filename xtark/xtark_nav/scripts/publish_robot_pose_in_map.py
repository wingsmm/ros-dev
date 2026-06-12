#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Publish the robot base pose in a map-like frame for Android map overlays."""

from __future__ import print_function

import rospy
import tf
from geometry_msgs.msg import PoseStamped


def _get_positive_float_param(name, default):
    value = float(rospy.get_param(name, default))
    if value <= 0.0:
        rospy.logwarn("%s must be positive; using %.3f", name, default)
        return float(default)
    return value


def _build_pose(frame_id, stamp, trans, rot):
    msg = PoseStamped()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.pose.position.x = trans[0]
    msg.pose.position.y = trans[1]
    msg.pose.position.z = trans[2]
    msg.pose.orientation.x = rot[0]
    msg.pose.orientation.y = rot[1]
    msg.pose.orientation.z = rot[2]
    msg.pose.orientation.w = rot[3]
    return msg


def main():
    rospy.init_node("robot_pose_in_map_publisher")

    map_frame = rospy.get_param("~map_frame", "map")
    base_frame = rospy.get_param("~base_frame", "base_footprint")
    pose_topic = rospy.get_param("~pose_topic", "/robot_pose_in_map")
    rate_hz = _get_positive_float_param("~rate", 10.0)
    timeout_sec = _get_positive_float_param("~transform_timeout", 0.3)

    listener = tf.TransformListener()
    pub = rospy.Publisher(pose_topic, PoseStamped, queue_size=10)
    rate = rospy.Rate(rate_hz)

    rospy.loginfo(
        "publishing %s -> %s as %s at %.2f Hz",
        map_frame,
        base_frame,
        pose_topic,
        rate_hz,
    )

    while not rospy.is_shutdown():
        stamp = rospy.Time(0)
        try:
            listener.waitForTransform(
                map_frame,
                base_frame,
                stamp,
                rospy.Duration(timeout_sec),
            )
            trans, rot = listener.lookupTransform(
                map_frame,
                base_frame,
                stamp,
            )
            latest_common_time = listener.getLatestCommonTime(map_frame, base_frame)
            pub.publish(_build_pose(map_frame, latest_common_time, trans, rot))

        except (
            tf.LookupException,
            tf.ConnectivityException,
            tf.ExtrapolationException,
            tf.Exception,
        ) as exc:
            rospy.logwarn_throttle(2.0, "robot_pose_in_map TF failed: %s", exc)

        rate.sleep()


if __name__ == "__main__":
    main()
