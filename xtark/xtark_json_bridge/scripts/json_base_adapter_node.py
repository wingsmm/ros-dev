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
from std_msgs.msg import Float32
from tf.transformations import euler_from_quaternion


def clamp(value, limit):
    if limit <= 0:
        return value
    return max(-limit, min(limit, value))


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

        cmd_topic = rospy.get_param("~cmd_vel_topic", "/cmd_vel")
        odom_topic = rospy.get_param("~odom_topic", "/odom")
        voltage_topic = rospy.get_param("~voltage_topic", "/voltage")

        self.cmd_pub = rospy.Publisher(cmd_topic, Twist, queue_size=1)
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.last_cmd_time = 0.0
        self.stop_sent = True
        self.latest_voltage = None

        rospy.Subscriber(odom_topic, Odometry, self.on_odom, queue_size=10)
        rospy.Subscriber(voltage_topic, Float32, self.on_voltage, queue_size=2)

        rospy.Timer(rospy.Duration(0.05), self.watchdog)
        rospy.Timer(rospy.Duration(1.0 / max(self.status_send_rate_hz, 0.1)), self.send_status)

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

        payload = {
            "type": "odom_base",
            "stamp_ms": int(time.time() * 1000),
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "yaw": yaw,
            "linear_x": msg.twist.twist.linear.x,
            "linear_y": msg.twist.twist.linear.y,
            "angular_z": msg.twist.twist.angular.z,
        }
        self.broadcast(payload)

    def on_voltage(self, msg):
        self.latest_voltage = float(msg.data)

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
