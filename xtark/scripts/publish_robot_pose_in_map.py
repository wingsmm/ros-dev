#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Publish base_footprint pose in map frame for Android SLAM map overlay."""

from __future__ import print_function

import rospy
import tf
from geometry_msgs.msg import PoseStamped


def main():
    rospy.init_node("robot_pose_in_map_publisher")

    listener = tf.TransformListener()
    pub = rospy.Publisher("/robot_pose_in_map", PoseStamped, queue_size=10)

    map_frame = rospy.get_param("~map_frame", "map")
    base_frame = rospy.get_param("~base_frame", "base_footprint")
    rate_hz = rospy.get_param("~rate", 10.0)

    rate = rospy.Rate(rate_hz)

    while not rospy.is_shutdown():
        try:
            listener.waitForTransform(
                map_frame,
                base_frame,
                rospy.Time(0),
                rospy.Duration(0.3),
            )
            trans, rot = listener.lookupTransform(
                map_frame,
                base_frame,
                rospy.Time(0),
            )

            msg = PoseStamped()
            msg.header.stamp = rospy.Time.now()
            msg.header.frame_id = map_frame
            msg.pose.position.x = trans[0]
            msg.pose.position.y = trans[1]
            msg.pose.position.z = trans[2]
            msg.pose.orientation.x = rot[0]
            msg.pose.orientation.y = rot[1]
            msg.pose.orientation.z = rot[2]
            msg.pose.orientation.w = rot[3]

            pub.publish(msg)

        except Exception as exc:
            rospy.logwarn_throttle(2.0, "robot_pose_in_map TF failed: %s", exc)

        rate.sleep()


if __name__ == "__main__":
    main()
