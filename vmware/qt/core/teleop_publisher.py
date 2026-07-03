"""ROS1 /cmd_vel publisher for VMware Qt teleop (VM local, no SSH)."""

import logging
import os

logger = logging.getLogger(__name__)

try:
    import rospy
    from geometry_msgs.msg import Twist

    _ROSPY_AVAILABLE = True
except ImportError:
    rospy = None
    Twist = None
    _ROSPY_AVAILABLE = False


class TeleopPublisher(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self._ready = False
        self._init_error = ""
        self._pub = None

    @property
    def is_available(self):
        return _ROSPY_AVAILABLE

    @property
    def init_error(self):
        return self._init_error

    def ensure_ready(self):
        if self._ready:
            return True, ""
        if self._init_error:
            return False, self._init_error
        if not _ROSPY_AVAILABLE:
            self._init_error = "rospy 不可用（请在 VM ROS Melodic 环境运行）"
            return False, self._init_error

        if not self.cfg.ros_ip:
            self._init_error = "ROS_IP 未设置，无法发布 /cmd_vel"
            return False, self._init_error

        os.environ["ROS_MASTER_URI"] = self.cfg.ros_master_uri
        os.environ["ROS_IP"] = self.cfg.ros_ip
        if "ROS_HOSTNAME" in os.environ:
            del os.environ["ROS_HOSTNAME"]

        try:
            if not rospy.core.is_initialized():
                rospy.init_node(
                    "vmware_qt_teleop",
                    anonymous=True,
                    disable_signals=True,
                )
            queue_size = 5
            self._pub = rospy.Publisher(
                self.cfg.cmd_vel_topic,
                Twist,
                queue_size=queue_size,
            )
            rospy.sleep(0.05)
            self._ready = True
            logger.info(
                "teleop publisher ready topic=%s", self.cfg.cmd_vel_topic
            )
            return True, ""
        except Exception as exc:
            self._init_error = str(exc)
            logger.exception("teleop rospy init failed")
            return False, self._init_error

    def publish_velocity(self, linear_x, linear_y, angular_z):
        ok, err = self.ensure_ready()
        if not ok:
            return False, err
        twist = Twist()
        twist.linear.x = float(linear_x)
        twist.linear.y = float(linear_y)
        twist.angular.z = float(angular_z)
        self._pub.publish(twist)
        return True, ""

    def stop(self, repeat=3):
        if not self._ready or self._pub is None:
            return
        twist = Twist()
        count = max(1, int(repeat))
        for _ in range(count):
            self._pub.publish(twist)

    def shutdown(self):
        self.stop(repeat=3)
        self._ready = False
        self._pub = None
