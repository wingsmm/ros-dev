#!/usr/bin/env python2
"""Bridge stdin velocity commands to ROS1 /cmd_vel (ROS Melodic / python2)."""

import os
import select
import sys
import time

import rospy
from geometry_msgs.msg import Twist


def _float_env(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _zero_twist():
    return Twist()


def _parse_line(line):
    if line == "stop" or line == "s":
        return _zero_twist(), True
    parts = line.split()
    if len(parts) < 3:
        return None, False
    twist = Twist()
    twist.linear.x = float(parts[0])
    twist.linear.y = float(parts[1])
    twist.angular.z = float(parts[2])
    return twist, False


def main():
    topic = os.environ.get("CMD_VEL_TOPIC", "/cmd_vel")
    publish_hz = max(1.0, _float_env("TELEOP_REPEAT_HZ", "10"))
    watchdog_s = max(0.2, _float_env("TELEOP_WATCHDOG_S", "0.35"))
    rospy.init_node("vmware_qt_teleop", anonymous=True, disable_signals=True)
    pub = rospy.Publisher(topic, Twist, queue_size=5)
    rospy.sleep(0.3)
    rospy.loginfo(
        "teleop bridge ready topic=%s hz=%.1f watchdog=%.2fs",
        topic,
        publish_hz,
        watchdog_s,
    )

    rate = rospy.Rate(publish_hz)
    active = _zero_twist()
    last_cmd_at = 0.0
    published_stop = True

    while not rospy.is_shutdown():
        readable, _, _ = select.select([sys.stdin], [], [], 0.0)
        for stream in readable:
            raw = stream.readline()
            if raw == "":
                rospy.loginfo("teleop bridge stdin closed")
                pub.publish(_zero_twist())
                return
            line = raw.strip()
            if not line:
                continue
            try:
                parsed, is_stop = _parse_line(line)
            except ValueError:
                rospy.logwarn("teleop bridge ignored invalid line: %s", line)
                continue
            if parsed is None:
                continue
            active = parsed
            last_cmd_at = time.time()
            published_stop = False
            if is_stop:
                pub.publish(active)
                published_stop = True
                rospy.loginfo("teleop bridge stop")

        if last_cmd_at and time.time() - last_cmd_at > watchdog_s:
            active = _zero_twist()
            if not published_stop:
                pub.publish(active)
                published_stop = True
        elif not published_stop:
            pub.publish(active)

        rate.sleep()


if __name__ == "__main__":
    main()
