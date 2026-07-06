#!/usr/bin/env python2
"""Read velocity lines from stdin and publish geometry_msgs/Twist (ROS1 Melodic)."""

import os
import sys

import rospy
from geometry_msgs.msg import Twist


def main():
    topic = os.environ.get("CMD_VEL_TOPIC", "/cmd_vel")
    rospy.init_node("vmware_qt_teleop", anonymous=True, disable_signals=True)
    pub = rospy.Publisher(topic, Twist, queue_size=5)
    rospy.sleep(0.05)
    rospy.loginfo("teleop bridge ready topic=%s", topic)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        twist = Twist()
        repeat = 1
        if line == "stop" or line == "s":
            repeat = 3
        else:
            parts = line.split()
            if len(parts) < 3:
                continue
            twist.linear.x = float(parts[0])
            twist.linear.y = float(parts[1])
            twist.angular.z = float(parts[2])
        for _ in range(repeat):
            pub.publish(twist)
            if repeat > 1:
                rospy.sleep(0.02)


if __name__ == "__main__":
    main()
