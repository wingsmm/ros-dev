#!/usr/bin/env python3
"""Quick link check: xtark JSON TCP + optional RK ping."""
from __future__ import print_function

import json
import socket
import subprocess
import sys
import time

XTARK_HOST = "192.168.1.168"
XTARK_PORT = 8765
RK_HOST = "192.168.1.163"


def ping(host):
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", host],
                capture_output=True,
                text=True,
            )
        else:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True,
                text=True,
            )
        return r.returncode == 0
    except Exception as exc:
        print("ping {} err: {}".format(host, exc))
        return False


def check_xtark_json(host, port, wait_sec=3.0):
    print("--- xtark JSON {}:{} ---".format(host, port))
    try:
        sock = socket.create_connection((host, port), timeout=5.0)
    except OSError as exc:
        print("FAIL connect: {}".format(exc))
        return False
    sock.settimeout(wait_sec)
    stop = json.dumps(
        {"type": "cmd_vel", "linear_x": 0, "linear_y": 0, "angular_z": 0}
    ) + "\n"
    sock.sendall(stop.encode("utf-8"))
    print("OK  sent stop cmd_vel")
    got = []
    buffer = ""
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line:
                got.append(line)
    sock.close()
    if not got:
        print("WARN connected but no feedback in {:.0f}s (adapter may be down)".format(wait_sec))
        return True
    for line in got[:5]:
        print("RX  " + line[:200])
    types = []
    for line in got:
        try:
            types.append(json.loads(line).get("type"))
        except ValueError:
            pass
    print("OK  feedback types: {}".format(types))
    return True


def main():
    print("=== network ===")
    for name, host in [("xtark", XTARK_HOST), ("rk3568", RK_HOST)]:
        ok = ping(host)
        print("{} {}: {}".format(host, name, "OK" if ok else "FAIL"))

    ok_xtark = check_xtark_json(XTARK_HOST, XTARK_PORT)
    print()
    print("=== summary ===")
    print("xtark JSON: {}".format("PASS" if ok_xtark else "FAIL"))
    print("RK /scan: run on RK/WSL with: export ROS_DOMAIN_ID=0 && ros2 topic hz /scan")
    return 0 if ok_xtark else 1


if __name__ == "__main__":
    sys.exit(main())
