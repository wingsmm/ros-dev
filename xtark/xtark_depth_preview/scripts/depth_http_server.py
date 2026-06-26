#!/usr/bin/env python
"""Serve the latest raw ROS1 depth frame over a pull-only HTTP endpoint.

The server intentionally does no colorization, compression, mapping or point
cloud work. It keeps one latest frame and lets the PC pull at its own rate.
"""

from __future__ import division

import json
import struct
import threading

import rospy
from sensor_msgs.msg import CameraInfo, Image

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
except ImportError:  # pragma: no cover - Python 3 development fallback
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn


MAGIC = b"XTD1"
MAX_FRAME_BYTES = 32 * 1024 * 1024


class LatestDepth(object):
  def __init__(self):
    self._lock = threading.Lock()
    self._frame = None
    self._camera_info = None

  def set_frame(self, msg):
    data = bytes(bytearray(msg.data))
    if not data or len(data) > MAX_FRAME_BYTES:
      rospy.logwarn_throttle(5.0, "ignore depth HTTP frame bytes=%d", len(data))
      return
    header = {
      "stamp_sec": int(msg.header.stamp.secs),
      "stamp_nsec": int(msg.header.stamp.nsecs),
      "frame_id": str(msg.header.frame_id),
      "height": int(msg.height),
      "width": int(msg.width),
      "encoding": str(msg.encoding),
      "is_bigendian": int(msg.is_bigendian),
      "step": int(msg.step),
      "data_bytes": len(data),
    }
    with self._lock:
      self._frame = (header, data)

  def set_camera_info(self, msg):
    info = {
      "stamp_sec": int(msg.header.stamp.secs),
      "stamp_nsec": int(msg.header.stamp.nsecs),
      "frame_id": str(msg.header.frame_id),
      "height": int(msg.height),
      "width": int(msg.width),
      "distortion_model": str(msg.distortion_model),
      "d": [float(value) for value in msg.D],
      "k": [float(value) for value in msg.K],
      "r": [float(value) for value in msg.R],
      "p": [float(value) for value in msg.P],
    }
    with self._lock:
      self._camera_info = info

  def get_frame(self):
    with self._lock:
      return self._frame

  def get_camera_info(self):
    with self._lock:
      return self._camera_info


class ThreadedHttpServer(ThreadingMixIn, HTTPServer):
  daemon_threads = True


def make_handler(store):
  class DepthHttpHandler(BaseHTTPRequestHandler):
    server_version = "xtark-depth-http/1.0"

    def log_message(self, _format, *_args):
      return

    def _send_json(self, code, value):
      body = json.dumps(value, separators=(",", ":"))
      if not isinstance(body, bytes):
        body = body.encode("utf-8")
      self.send_response(code)
      self.send_header("Content-Type", "application/json")
      self.send_header("Content-Length", str(len(body)))
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      self.wfile.write(body)

    def do_GET(self):
      path = self.path.split("?", 1)[0]
      if path == "/healthz":
        self._send_json(200, {
          "depth_ready": store.get_frame() is not None,
          "camera_info_ready": store.get_camera_info() is not None,
        })
        return
      if path == "/v1/depth/camera_info":
        info = store.get_camera_info()
        if info is None:
          self._send_json(503, {"error": "camera_info unavailable"})
        else:
          self._send_json(200, info)
        return
      if path != "/v1/depth/latest":
        self._send_json(404, {"error": "not found"})
        return

      frame = store.get_frame()
      if frame is None:
        self._send_json(503, {"error": "depth unavailable"})
        return
      header, data = frame
      header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
      body_size = len(MAGIC) + 4 + len(header_bytes) + len(data)
      self.send_response(200)
      self.send_header("Content-Type", "application/x-xtark-depth")
      self.send_header("Content-Length", str(body_size))
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      self.wfile.write(MAGIC)
      self.wfile.write(struct.pack("!I", len(header_bytes)))
      self.wfile.write(header_bytes)
      self.wfile.write(data)

  return DepthHttpHandler


def main():
  rospy.init_node("depth_http_server")
  input_topic = rospy.get_param("~input_topic", "/camera/depth/image_raw")
  camera_info_topic = rospy.get_param("~camera_info_topic", "/camera/depth/camera_info")
  host = rospy.get_param("~host", "0.0.0.0")
  port = int(rospy.get_param("~port", 8082))
  store = LatestDepth()
  rospy.Subscriber(input_topic, Image, store.set_frame, queue_size=1, buff_size=2**22)
  rospy.Subscriber(camera_info_topic, CameraInfo, store.set_camera_info, queue_size=1)
  server = ThreadedHttpServer((host, port), make_handler(store))
  thread = threading.Thread(target=server.serve_forever)
  thread.daemon = True
  thread.start()
  rospy.loginfo("depth HTTP %s:%d raw=%s info=%s", host, port, input_topic, camera_info_topic)
  try:
    rospy.spin()
  finally:
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
  main()
