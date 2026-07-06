#!/usr/bin/env python
from __future__ import print_function

import argparse
import json
import socket
import time


def main():
    parser = argparse.ArgumentParser(description="Send one JSON cmd_vel line.")
    parser.add_argument("--host", default="192.168.1.168")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--linear-x", type=float, default=0.0)
    parser.add_argument("--linear-y", type=float, default=0.0)
    parser.add_argument("--angular-z", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--rate", type=float, default=10.0)
    args = parser.parse_args()

    sock = socket.create_connection((args.host, args.port), timeout=5.0)
    try:
        start = time.time()
        seq = 0
        while True:
            payload = {
                "type": "cmd_vel",
                "seq": seq,
                "stamp_ms": int(time.time() * 1000),
                "linear_x": args.linear_x,
                "linear_y": args.linear_y,
                "angular_z": args.angular_z,
            }
            sock.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
            print(payload)
            seq += 1
            if args.duration <= 0 or time.time() - start >= args.duration:
                break
            time.sleep(1.0 / max(args.rate, 0.1))
    finally:
        stop = {
            "type": "cmd_vel",
            "stamp_ms": int(time.time() * 1000),
            "linear_x": 0.0,
            "linear_y": 0.0,
            "angular_z": 0.0,
        }
        sock.sendall((json.dumps(stop, separators=(",", ":")) + "\n").encode("utf-8"))
        sock.close()


if __name__ == "__main__":
    main()
