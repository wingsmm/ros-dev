#!/usr/bin/env python3
"""Keyboard teleop for the PLJ motor-control HTTP service.

This script sends only documented GET requests to the motor Web service. It does
not require ROS 2 and does not modify any remote files.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
import urllib.parse
import urllib.request


HELP = r"""
PLJ keyboard control

Movement:
  w / s        track forward / backward
  x            stop track

Rear drive:
  i / ,        rear drive forward / backward
  a / d        rear differential left / right
  k            stop rear drive

Lift:
  u            lift both motors up
  j            lower both motors
  h            stop lift motors

Steering:
  [ / ]        steering target -= step / += step
  p            stop steering motor

Speed:
  + / =        increase speed
  - / _        decrease speed

Safety:
  space        stop track, rear drive, steering, and lift
  ?            show this help
  q / Ctrl+C   stop all and quit
"""


class SingleKeyReader:
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
        tty.setcbreak(self._stdin_fd)
        return self._getch_unix

    def __exit__(self, exc_type, exc, tb):
        if not sys.platform.startswith("win"):
            self._termios.tcsetattr(
                self._stdin_fd, self._termios.TCSADRAIN, self._old_attrs
            )

    def _getch_windows(self):
        ch = self._msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            self._msvcrt.getwch()
            return ""
        return ch

    def _getch_unix(self):
        return sys.stdin.read(1)


class MotorClient:
    def __init__(self, base_url: str, timeout: float, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dry_run = dry_run

    def get(self, path: str, **params):
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        if self.dry_run:
            print(f"DRY {url}")
            return

        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                body = response.read(160).decode("utf-8", errors="replace")
            print(f"OK  {url}  {body[:120]}")
        except Exception as exc:  # noqa: BLE001 - command-line diagnostics
            print(f"ERR {url}  {exc}")


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def stop_lift(client: MotorClient):
    for motor in (1, 2):
        client.get("/forward_stop_1", motor=motor)
        client.get("/backward_stop_1", motor=motor)


def lift_up(client: MotorClient):
    for motor in (1, 2):
        client.get("/forward_1", motor=motor)


def lower_both(client: MotorClient):
    client.get("/backward_tongbu")


def stop_rear(client: MotorClient):
    for motor in (1, 2):
        client.get("/chassis_motor_run", id=motor, speed=0, dir=0)


def rear_forward(client: MotorClient, speed: int):
    for motor in (1, 2):
        client.get("/chassis_motor_run", id=motor, speed=speed, dir=1)


def rear_backward(client: MotorClient, speed: int):
    for motor in (1, 2):
        client.get("/chassis_motor_run", id=motor, speed=speed, dir=0)


def rear_left(client: MotorClient, speed: int):
    client.get("/chassis_motor_run", id=1, speed=speed, dir=0)
    client.get("/chassis_motor_run", id=2, speed=speed, dir=1)


def rear_right(client: MotorClient, speed: int):
    client.get("/chassis_motor_run", id=2, speed=speed, dir=0)
    client.get("/chassis_motor_run", id=1, speed=speed, dir=1)


def track(client: MotorClient, speed: int, direction: int):
    client.get("/dipan_motor_run", id=1, speed=speed, dir=direction)


def stop_track(client: MotorClient):
    track(client, 0, 0)


def steer(client: MotorClient, target_position: int, speed: int):
    client.get(
        "/zhuanxiang_motor_run",
        target_position=target_position,
        zhuanxiang_speed=speed,
    )


def stop_steer(client: MotorClient, target_position: int):
    steer(client, target_position, 0)


def stop_all(client: MotorClient, target_position: int):
    stop_track(client)
    stop_rear(client)
    stop_steer(client, target_position)
    stop_lift(client)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Keyboard control for PLJ motor-control HTTP service"
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="Motor Web base URL, e.g. http://172.0.0.67:8080",
    )
    parser.add_argument("--speed", type=int, default=30, help="Initial speed 0-100")
    parser.add_argument("--speed-step", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--steer-position", type=int, default=3600)
    parser.add_argument("--steer-step", type=int, default=400)
    parser.add_argument("--steer-speed", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    speed = clamp(args.speed, 0, 100)
    steer_position = args.steer_position
    client = MotorClient(args.base_url, timeout=args.timeout, dry_run=args.dry_run)

    print(HELP)
    print(f"base_url={args.base_url} speed={speed} steer_position={steer_position}")

    with SingleKeyReader() as getch:
        try:
            while True:
                key = getch()
                if not key:
                    continue

                if key in ("q", "\x03"):
                    print("quit: stopping all")
                    stop_all(client, steer_position)
                    return 0
                if key == "?":
                    print(HELP)
                elif key == " ":
                    print("stop all")
                    stop_all(client, steer_position)
                elif key in ("+", "="):
                    speed = clamp(speed + args.speed_step, 0, 100)
                    print(f"speed={speed}")
                elif key in ("-", "_"):
                    speed = clamp(speed - args.speed_step, 0, 100)
                    print(f"speed={speed}")
                elif key == "w":
                    print(f"track forward speed={speed}")
                    track(client, speed, 1)
                elif key == "s":
                    print(f"track backward speed={speed}")
                    track(client, speed, 0)
                elif key == "x":
                    print("track stop")
                    stop_track(client)
                elif key == "i":
                    print(f"rear forward speed={speed}")
                    rear_forward(client, speed)
                elif key == ",":
                    print(f"rear backward speed={speed}")
                    rear_backward(client, speed)
                elif key == "a":
                    print(f"rear left speed={speed}")
                    rear_left(client, speed)
                elif key == "d":
                    print(f"rear right speed={speed}")
                    rear_right(client, speed)
                elif key == "k":
                    print("rear stop")
                    stop_rear(client)
                elif key == "u":
                    print("lift both up")
                    lift_up(client)
                elif key == "j":
                    print("lower both")
                    lower_both(client)
                elif key == "h":
                    print("lift stop")
                    stop_lift(client)
                elif key == "[":
                    steer_position -= args.steer_step
                    print(f"steer target={steer_position}")
                    steer(client, steer_position, args.steer_speed)
                elif key == "]":
                    steer_position += args.steer_step
                    print(f"steer target={steer_position}")
                    steer(client, steer_position, args.steer_speed)
                elif key == "p":
                    print("steer stop")
                    stop_steer(client, steer_position)

                time.sleep(0.03)
        except KeyboardInterrupt:
            print("\nCtrl+C: stopping all")
            with contextlib.suppress(Exception):
                stop_all(client, steer_position)
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
