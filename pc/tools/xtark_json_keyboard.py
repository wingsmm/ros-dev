#!/usr/bin/env python
from __future__ import print_function

import argparse
import json
import socket
import sys
import threading
import time


MSG = """
Reading from the keyboard  and Publishing to Twist!
---------------------------
Moving around:
   u    i    o         ^
   j    k    l       < v >
   m    ,    .

For Holonomic mode (strafing), hold down the shift key:
---------------------------
   U    I    O
   J    K    L
   M    <    >

t : up (+z)
b : down (-z)

anything else : stop

q/z : increase/decrease max speeds by 10%
w/x : increase/decrease only linear speed by 10%
e/c : increase/decrease only angular speed by 10%

CTRL-C to quit
"""

# 与 ~/ros_ws/src/xtark_ctl/scripts/xtark_twist_keyboard.py 保持一致
MOVE_BINDINGS = {
    "i": (1, 0, 0, 0),
    "o": (1, 0, 0, -1),
    "j": (0, 0, 0, 1),
    "l": (0, 0, 0, -1),
    "u": (1, 0, 0, 1),
    ",": (-1, 0, 0, 0),
    ".": (-1, 0, 0, 1),
    "m": (-1, 0, 0, -1),
    "O": (1, -1, 0, 0),
    "I": (1, 0, 0, 0),
    "J": (0, 1, 0, 0),
    "L": (0, -1, 0, 0),
    "U": (1, 1, 0, 0),
    "<": (-1, 0, 0, 0),
    ">": (-1, -1, 0, 0),
    "M": (-1, 1, 0, 0),
    "t": (0, 0, 1, 0),
    "k": (0, 0, 0, 0),
    " ": (0, 0, 0, 0),
    "b": (0, 0, -1, 0),
    "A": (1, 0, 0, 0),
    "B": (-1, 0, 0, 0),
    "C": (0, 0, 0, -1),
    "D": (0, 0, 0, 1),
}

SPEED_BINDINGS = {
    "q": (1.1, 1.1),
    "z": (0.9, 0.9),
    "w": (1.1, 1),
    "x": (0.9, 1),
    "e": (1, 1.1),
    "c": (1, 0.9),
}


class SingleKeyReader(object):
    def __enter__(self):
        if sys.platform.startswith("win"):
            import msvcrt

            self._msvcrt = msvcrt
            return self._getch_windows

        import termios
        import tty

        self._termios = termios
        self._stdin_fd = sys.stdin.fileno()
        self._old_attrs = termios.tcgetattr(self._stdin_fd)
        tty.setraw(self._stdin_fd)
        return self._getch_unix

    def __exit__(self, exc_type, exc, tb):
        if not sys.platform.startswith("win"):
            self._termios.tcsetattr(
                self._stdin_fd, self._termios.TCSADRAIN, self._old_attrs
            )

    def _getch_windows(self):
        ch = self._msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            second = self._msvcrt.getwch()
            return {
                "H": "A",  # up
                "P": "B",  # down
                "M": "C",  # right
                "K": "D",  # left
            }.get(second, "")
        return ch

    def _getch_unix(self):
        return sys.stdin.read(1)


class JsonTcpClient(object):
    def __init__(self, host, port, recv_feedback, feedback_rate):
        self.host = host
        self.port = int(port)
        self.recv_feedback = recv_feedback
        self.feedback_rate = float(feedback_rate)
        self.sock = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.recv_thread = None
        self.seq = 0
        self.last_feedback_print = 0.0

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=5.0)
        self.sock.settimeout(0.5)
        if self.recv_feedback:
            self.recv_thread = threading.Thread(target=self._recv_loop)
            self.recv_thread.daemon = True
            self.recv_thread.start()

    def close(self):
        self.stop_event.set()
        with self.lock:
            sock = self.sock
            self.sock = None
        if sock is not None:
            try:
                sock.close()
            except socket.error:
                pass
        if self.recv_thread is not None:
            self.recv_thread.join(timeout=1.0)

    def send_cmd_vel(self, linear_x, linear_y, angular_z):
        payload = {
            "type": "cmd_vel",
            "seq": self.seq,
            "stamp_ms": int(time.time() * 1000),
            "linear_x": linear_x,
            "linear_y": linear_y,
            "angular_z": angular_z,
        }
        self.seq += 1
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        with self.lock:
            if self.sock is None:
                return False
            try:
                self.sock.sendall(data)
            except socket.error as exc:
                print("send failed: {}".format(exc))
                try:
                    self.sock.close()
                except socket.error:
                    pass
                self.sock = None
                return False
        return True

    def _recv_loop(self):
        buffer = ""
        while not self.stop_event.is_set():
            with self.lock:
                sock = self.sock
            if sock is None:
                break
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except socket.error:
                break
            if not chunk:
                break
            if not isinstance(chunk, str):
                chunk = chunk.decode("utf-8", errors="replace")
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    self._print_feedback(line)

    def _print_feedback(self, line):
        try:
            msg = json.loads(line)
        except ValueError:
            return
        msg_type = msg.get("type")
        if msg_type == "odom_base":
            if not self.should_print_feedback():
                return
            print(
                "odom x={x:.3f} y={y:.3f} yaw={yaw:.3f} "
                "vx={linear_x:.3f} vy={linear_y:.3f} wz={angular_z:.3f}".format(
                    x=msg.get("x", 0.0),
                    y=msg.get("y", 0.0),
                    yaw=msg.get("yaw", 0.0),
                    linear_x=msg.get("linear_x", 0.0),
                    linear_y=msg.get("linear_y", 0.0),
                    angular_z=msg.get("angular_z", 0.0),
                )
            )
        elif msg_type == "base_status":
            print(
                "status online={online} estop={estop} battery_v={battery_v}".format(
                    online=msg.get("online"),
                    estop=msg.get("estop"),
                    battery_v=msg.get("battery_v"),
                )
            )

    def should_print_feedback(self):
        if self.feedback_rate <= 0:
            return True
        now = time.time()
        if now - self.last_feedback_print < 1.0 / self.feedback_rate:
            return False
        self.last_feedback_print = now
        return True


def vels(speed, turn):
    return "currently:\tspeed %s\tturn %s " % (speed, turn)


def parse_args():
    parser = argparse.ArgumentParser(
        description="xtark JSON keyboard teleop (logic from xtark_twist_keyboard.py)"
    )
    parser.add_argument("--host", default="192.168.1.169")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--speed", type=float, default=0.5)
    parser.add_argument("--turn", type=float, default=1.0)
    parser.add_argument(
        "--no-feedback",
        action="store_true",
        help="do not print odom_base / base_status from bridge",
    )
    parser.add_argument(
        "--feedback-rate",
        type=float,
        default=2.0,
        help="max odom feedback print rate in Hz; use 0 to print every message",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    client = JsonTcpClient(
        args.host,
        args.port,
        recv_feedback=not args.no_feedback,
        feedback_rate=args.feedback_rate,
    )

    speed = args.speed
    turn = args.turn
    x = 0
    y = 0
    z = 0
    th = 0
    status = 0

    print(MSG)
    print(vels(speed, turn))
    print("json target: {host}:{port}".format(host=args.host, port=args.port))

    try:
        client.connect()
    except socket.error as exc:
        print("connect failed: {}".format(exc))
        return 1

    try:
        with SingleKeyReader() as getch:
            while True:
                key = getch()
                if not key:
                    continue

                if key in MOVE_BINDINGS:
                    x, y, z, th = MOVE_BINDINGS[key]
                    client.send_cmd_vel(x * speed, y * speed, th * turn)
                elif key in SPEED_BINDINGS:
                    speed = speed * SPEED_BINDINGS[key][0]
                    turn = turn * SPEED_BINDINGS[key][1]
                    print(vels(speed, turn))
                    if status == 14:
                        print(MSG)
                    status = (status + 1) % 15
                else:
                    x = 0
                    y = 0
                    z = 0
                    th = 0
                    if key == "\x03":
                        break

    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(exc)
    finally:
        try:
            client.send_cmd_vel(0.0, 0.0, 0.0)
        except Exception:
            pass
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
