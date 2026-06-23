#!/usr/bin/env python
from __future__ import print_function

import json
import math
import socket
import threading
import time

import rospy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32
from tf.transformations import euler_from_quaternion

from warning_scan_math import compute_front_min_range


def clamp(value, limit):
    if limit <= 0:
        return value
    return max(-limit, min(limit, value))


def normalize_angle(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def is_finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(number) or math.isinf(number))


class JsonBaseAdapter(object):
    def __init__(self):
        self.host = rospy.get_param("~host", "0.0.0.0")
        self.port = int(rospy.get_param("~port", 8765))
        self.cmd_timeout_sec = float(rospy.get_param("~cmd_timeout_sec", 0.5))
        self.max_linear_x = float(rospy.get_param("~max_linear_x", 0.3))
        self.max_linear_y = float(rospy.get_param("~max_linear_y", 0.3))
        self.max_angular_z = float(rospy.get_param("~max_angular_z", 0.8))
        self.odom_send_rate_hz = float(rospy.get_param("~odom_send_rate_hz", 20.0))
        self.status_send_rate_hz = float(rospy.get_param("~status_send_rate_hz", 2.0))
        self.scan_warning_send_rate_hz = float(
            rospy.get_param("~scan_warning_send_rate_hz", 10.0)
        )
        self.laser_scan_send_rate_hz = float(
            rospy.get_param("~laser_scan_send_rate_hz", 10.0)
        )
        self.laser_scan_stride = max(1, int(rospy.get_param("~laser_scan_stride", 1)))
        self.scan_stale_sec = float(rospy.get_param("~scan_stale_sec", 1.0))

        cmd_topic = rospy.get_param("~cmd_vel_topic", "/cmd_vel")
        odom_topic = rospy.get_param("~odom_topic", "/odom")
        voltage_topic = rospy.get_param("~voltage_topic", "/voltage")
        scan_topic = rospy.get_param("~scan_topic", "/scan")

        self.cmd_pub = rospy.Publisher(cmd_topic, Twist, queue_size=1)
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.last_cmd_time = 0.0
        self.stop_sent = True
        self.latest_voltage = None
        self.last_pose_sample = None
        self.latest_front_min = float("inf")
        self.last_scan_time = 0.0
        self.latest_scan_msg = None
        self.latest_scan_lock = threading.Lock()

        rospy.Subscriber(odom_topic, Odometry, self.on_odom, queue_size=10)
        rospy.Subscriber(voltage_topic, Float32, self.on_voltage, queue_size=2)
        rospy.Subscriber(scan_topic, LaserScan, self.on_scan, queue_size=5)

        rospy.Timer(rospy.Duration(0.05), self.watchdog)
        rospy.Timer(rospy.Duration(1.0 / max(self.status_send_rate_hz, 0.1)), self.send_status)
        rospy.Timer(
            rospy.Duration(1.0 / max(self.scan_warning_send_rate_hz, 0.1)),
            self.send_scan_warning,
        )
        rospy.Timer(
            rospy.Duration(1.0 / max(self.laser_scan_send_rate_hz, 0.1)),
            self.send_laser_scan,
        )

        self.server_thread = threading.Thread(target=self.run_server)
        self.server_thread.daemon = True
        self.server_thread.start()

        rospy.loginfo("json_base_adapter listening on %s:%d", self.host, self.port)

    def run_server(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(5)
        srv.settimeout(0.5)

        while not rospy.is_shutdown():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except socket.error as exc:
                rospy.logwarn("accept failed: %s", exc)
                continue

            rospy.loginfo("json client connected: %s:%s", addr[0], addr[1])
            with self.clients_lock:
                self.clients.add(conn)
            th = threading.Thread(target=self.handle_client, args=(conn, addr))
            th.daemon = True
            th.start()

        srv.close()

    def handle_client(self, conn, addr):
        buffer = ""
        conn.settimeout(0.5)
        try:
            while not rospy.is_shutdown():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break

                if not isinstance(data, str):
                    data = data.decode("utf-8")
                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self.handle_json_line(line)
        except Exception as exc:
            rospy.logwarn("json client %s:%s error: %s", addr[0], addr[1], exc)
        finally:
            with self.clients_lock:
                self.clients.discard(conn)
            try:
                conn.close()
            except socket.error:
                pass
            rospy.loginfo("json client disconnected: %s:%s", addr[0], addr[1])

    def handle_json_line(self, line):
        try:
            msg = json.loads(line)
        except ValueError:
            rospy.logwarn("invalid json: %s", line)
            return

        msg_type = msg.get("type")
        if msg_type == "cmd_vel":
            self.publish_cmd_vel(msg)
        else:
            rospy.logwarn("unsupported json type: %s", msg_type)

    def publish_cmd_vel(self, msg):
        twist = Twist()
        twist.linear.x = clamp(float(msg.get("linear_x", 0.0)), self.max_linear_x)
        twist.linear.y = clamp(float(msg.get("linear_y", 0.0)), self.max_linear_y)
        twist.angular.z = clamp(float(msg.get("angular_z", 0.0)), self.max_angular_z)
        self.cmd_pub.publish(twist)
        self.last_cmd_time = time.time()
        self.stop_sent = False

    def watchdog(self, _event):
        if self.stop_sent:
            return
        if time.time() - self.last_cmd_time <= self.cmd_timeout_sec:
            return
        self.cmd_pub.publish(Twist())
        self.stop_sent = True
        rospy.logwarn("cmd_vel timeout, published stop")

    def on_odom(self, msg):
        now = time.time()
        if not hasattr(self, "_last_odom_send"):
            self._last_odom_send = 0.0
        if now - self._last_odom_send < 1.0 / max(self.odom_send_rate_hz, 0.1):
            return
        self._last_odom_send = now

        q = msg.pose.pose.orientation
        quat = [q.x, q.y, q.z, q.w]
        try:
            _roll, _pitch, yaw = euler_from_quaternion(quat)
        except Exception:
            yaw = 0.0

        linear_x = msg.twist.twist.linear.x
        linear_y = msg.twist.twist.linear.y
        angular_z = msg.twist.twist.angular.z

        if (
            abs(linear_x) < 1e-6
            and abs(linear_y) < 1e-6
            and abs(angular_z) < 1e-6
            and self.last_pose_sample is not None
        ):
            last_time, last_x, last_y, last_yaw = self.last_pose_sample
            dt = max(now - last_time, 1e-6)
            linear_x = (msg.pose.pose.position.x - last_x) / dt
            linear_y = (msg.pose.pose.position.y - last_y) / dt
            angular_z = normalize_angle(yaw - last_yaw) / dt

        self.last_pose_sample = (
            now,
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            yaw,
        )

        payload = {
            "type": "odom_base",
            "stamp_ms": int(time.time() * 1000),
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "yaw": yaw,
            "linear_x": linear_x,
            "linear_y": linear_y,
            "angular_z": angular_z,
        }
        self.broadcast(payload)

    def on_voltage(self, msg):
        self.latest_voltage = float(msg.data)

    def on_scan(self, msg):
        ranges = list(msg.ranges)
        self.latest_front_min = compute_front_min_range(
            ranges, msg.angle_min, msg.angle_increment
        )
        self.last_scan_time = time.time()
        with self.latest_scan_lock:
            self.latest_scan_msg = msg

    @staticmethod
    def _clean_range(value, range_min, range_max):
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not is_finite_number(number):
            return None
        if number < range_min or number > range_max:
            return None
        return number

    def _scan_is_stale(self, now=None):
        now = time.time() if now is None else now
        return (
            self.last_scan_time <= 0.0
            or (now - self.last_scan_time) > self.scan_stale_sec
        )

    def send_laser_scan(self, _event):
        now = time.time()
        if self._scan_is_stale(now):
            return

        with self.latest_scan_lock:
            msg = self.latest_scan_msg
        if msg is None:
            return

        stride = self.laser_scan_stride
        ranges = list(msg.ranges)[::stride]
        if not ranges:
            return

        angle_min = float(msg.angle_min)
        angle_increment = float(msg.angle_increment) * stride
        angle_max = angle_min + angle_increment * (len(ranges) - 1)
        cleaned = [
            self._clean_range(r, msg.range_min, msg.range_max) for r in ranges
        ]
        stamp = msg.header.stamp
        stamp_ms = int(stamp.secs * 1000 + stamp.nsecs / 1000000)
        if stamp_ms <= 0:
            stamp_ms = int(now * 1000)

        frame_id = msg.header.frame_id
        if not frame_id:
            frame_id = "laser"

        payload = {
            "type": "laser_scan",
            "stamp_ms": stamp_ms,
            "frame_id": frame_id,
            "angle_min": angle_min,
            "angle_max": angle_max,
            "angle_increment": angle_increment,
            "range_min": float(msg.range_min),
            "range_max": float(msg.range_max),
            "ranges": cleaned,
        }
        self.broadcast(payload)

    def send_scan_warning(self, _event):
        now = time.time()
        stale = self._scan_is_stale(now)
        payload = {
            "type": "scan_warning",
            "stamp_ms": int(now * 1000),
            "front_min_m": None if stale else self.latest_front_min,
            "stale": stale,
        }
        self.broadcast(payload)

    def send_status(self, _event):
        payload = {
            "type": "base_status",
            "stamp_ms": int(time.time() * 1000),
            "online": True,
            "estop": False,
            "battery_v": self.latest_voltage,
            "mode": "auto",
            "error_code": 0,
        }
        self.broadcast(payload)

    def broadcast(self, payload):
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        dead = []
        with self.clients_lock:
            for conn in list(self.clients):
                try:
                    conn.sendall(data)
                except socket.error:
                    dead.append(conn)
            for conn in dead:
                self.clients.discard(conn)
                try:
                    conn.close()
                except socket.error:
                    pass


def main():
    rospy.init_node("json_base_adapter")
    JsonBaseAdapter()
    rospy.spin()


if __name__ == "__main__":
    main()
