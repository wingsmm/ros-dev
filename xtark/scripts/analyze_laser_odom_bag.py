#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Three-way rosbag analysis: /cmd_vel (intent) vs /odom vs /odom_laser.

Segments by motion class (forward/back/strafe/turn/stop), not just motion/stop.
"""

from __future__ import print_function

import argparse
import math
import sys
from collections import OrderedDict

import rosbag
from tf.transformations import euler_from_quaternion

VEL_EPS = 0.01
ANG_EPS = 0.02
MIN_SEG_S = 0.20
PAIR_DT = 0.06
RESPONSE_THRESH = 0.02
RESPONSE_MAX_S = 0.5

MOTION_LABELS = (
    "stop", "forward", "backward", "strafe_left", "strafe_right",
    "turn_left", "turn_right", "mixed",
)


def normalize_angle(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def yaw_from_quat(q):
    return euler_from_quaternion([q.x, q.y, q.z, q.w])[2]


def pose_xyyaw(msg):
    p = msg.pose.pose.position
    y = yaw_from_quat(msg.pose.pose.orientation)
    return p.x, p.y, y


def twist_xyz(msg):
    t = msg.twist.twist
    return t.linear.x, t.linear.y, t.angular.z


def cmd_xyz(msg):
    return msg.linear.x, msg.linear.y, msg.angular.z


def cmd_moving(msg):
    vx, vy, wz = cmd_xyz(msg)
    return abs(vx) > VEL_EPS or abs(vy) > VEL_EPS or abs(wz) > ANG_EPS


def cmd_class(msg):
    """Classify Qt/cmd_vel intent per sample."""
    vx, vy, wz = cmd_xyz(msg)
    if not cmd_moving(msg):
        return "stop"
    ax = abs(vx)
    ay = abs(vy)
    az = abs(wz)
    # rotation dominant
    if az > ANG_EPS and az >= max(ax, ay) * 0.6:
        return "turn_left" if wz > 0 else "turn_right"
    if ax >= ay and ax > VEL_EPS:
        return "forward" if vx > 0 else "backward"
    if ay > VEL_EPS:
        return "strafe_left" if vy > 0 else "strafe_right"
    if az > ANG_EPS:
        return "turn_left" if wz > 0 else "turn_right"
    return "mixed"


def segment_by_class(cmd_series):
    """Split when motion class changes (forward/back/strafe/turn/stop)."""
    if not cmd_series:
        return []
    segs = []
    t0, m0 = cmd_series[0]
    label = cmd_class(m0)
    seg_start = t0
    for ts, msg in cmd_series[1:]:
        lab = cmd_class(msg)
        if lab != label:
            if ts - seg_start >= MIN_SEG_S:
                segs.append((seg_start, ts, label))
            seg_start = ts
            label = lab
    t_end = cmd_series[-1][0]
    if t_end - seg_start >= MIN_SEG_S:
        segs.append((seg_start, t_end, label))
    return segs


def nearest_msg(series, t_sec, max_dt):
    best_dt = None
    best = None
    for ts, msg in series:
        dt = abs(ts - t_sec)
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = (ts, msg)
    if best_dt is not None and best_dt <= max_dt:
        return best
    return None


def msgs_in_range(series, t0, t1):
    return [(ts, m) for ts, m in series if t0 <= ts <= t1]


def rmse(vals):
    if not vals:
        return float("nan")
    return math.sqrt(sum(v * v for v in vals) / float(len(vals)))


def stat_line(name, vals):
    if not vals:
        print("  %s: (no data)" % name)
        return
    mean = sum(vals) / len(vals)
    print("  %s: mean=%.4f  max_abs=%.4f  rmse=%.4f  n=%d" % (
        name, mean, max(abs(v) for v in vals), rmse(vals), len(vals)))


def pose_delta_in_range(odom_series, t0, t1):
    chunk = msgs_in_range(odom_series, t0, t1)
    if len(chunk) < 2:
        return None
    x0, y0, yaw0 = pose_xyyaw(chunk[0][1])
    x1, y1, yaw1 = pose_xyyaw(chunk[-1][1])
    return {
        "dx": x1 - x0,
        "dy": y1 - y0,
        "dyaw_deg": math.degrees(normalize_angle(yaw1 - yaw0)),
        "dist": math.hypot(x1 - x0, y1 - y0),
    }


def avg_twist_in_range(odom_series, t0, t1):
    chunk = msgs_in_range(odom_series, t0, t1)
    if not chunk:
        return None
    sx = sy = sz = 0.0
    for _, m in chunk:
        vx, vy, wz = twist_xyz(m)
        sx += vx
        sy += vy
        sz += wz
    n = float(len(chunk))
    return sx / n, sy / n, sz / n


def avg_cmd_in_range(cmd_series, t0, t1):
    chunk = msgs_in_range(cmd_series, t0, t1)
    if not chunk:
        return None
    sx = sy = sz = 0.0
    for _, m in chunk:
        vx, vy, wz = cmd_xyz(m)
        sx += vx
        sy += vy
        sz += wz
    n = float(len(chunk))
    return sx / n, sy / n, sz / n


def sync_pose_errors(laser_series, wheel_series, t0, t1, w0_pose, l0_pose):
    ex, ey, eyaw = [], [], []
    w0x, w0y, w0yaw = w0_pose
    l0x, l0y, l0yaw = l0_pose
    for ts, lmsg in msgs_in_range(laser_series, t0, t1):
        pair = nearest_msg(wheel_series, ts, PAIR_DT)
        if pair is None:
            continue
        _, wmsg = pair
        wx, wy, wyaw = pose_xyyaw(wmsg)
        lx, ly, lyaw = pose_xyyaw(lmsg)
        ex.append((lx - l0x) - (wx - w0x))
        ey.append((ly - l0y) - (wy - w0y))
        eyaw.append(math.degrees(normalize_angle((lyaw - l0yaw) - (wyaw - w0yaw))))
    return ex, ey, eyaw


def label_cn(label):
    return {
        "stop": "停止",
        "forward": "前进",
        "backward": "后退",
        "strafe_left": "左移",
        "strafe_right": "右移",
        "turn_left": "左转",
        "turn_right": "右转",
        "mixed": "混合",
    }.get(label, label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bag")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    bag = rosbag.Bag(args.bag)
    cmd = []
    wheel = []
    laser = []
    for topic, msg, t in bag.read_messages(topics=["/cmd_vel", "/odom", "/odom_laser"]):
        ts = t.to_sec()
        if topic == "/cmd_vel":
            cmd.append((ts, msg))
        elif topic == "/odom":
            wheel.append((ts, msg))
        else:
            laser.append((ts, msg))
    bag.close()

    lines = []

    def out(s=""):
        lines.append(s)
        print(s)

    out("=== bag ===")
    out("  path: %s" % args.bag)
    out("  cmd_vel: %d  wheel /odom: %d  laser /odom_laser: %d" % (len(cmd), len(wheel), len(laser)))

    if not cmd or not wheel or not laser:
        out("[ERR] missing topics")
        return 1

    w0 = pose_xyyaw(wheel[0][1])
    l0 = pose_xyyaw(laser[0][1])

    # per-sample class histogram
    hist = OrderedDict((k, 0) for k in MOTION_LABELS)
    for _, m in cmd:
        hist[cmd_class(m)] = hist.get(cmd_class(m), 0) + 1

    out("=== /cmd_vel sample classes (per message) ===")
    for k in MOTION_LABELS:
        if hist.get(k, 0):
            out("  %s (%s): %d msgs" % (k, label_cn(k), hist[k]))

    segs = segment_by_class(cmd)
    out("")
    out("=== /cmd_vel segments by motion class ===")
    out("  count: %d (min duration %.2fs, split on class change)" % (len(segs), MIN_SEG_S))

    by_class = OrderedDict()

    for i, (t0, t1, label) in enumerate(segs):
        dur = t1 - t0
        ac = avg_cmd_in_range(cmd, t0, t1)
        dw = pose_delta_in_range(wheel, t0, t1)
        dl = pose_delta_in_range(laser, t0, t1)
        ex, ey, eyaw = sync_pose_errors(laser, wheel, t0, t1, w0, l0)
        pos_rmse = rmse([math.hypot(a, b) for a, b in zip(ex, ey)]) if ex else float("nan")
        yaw_rmse = rmse(eyaw) if eyaw else float("nan")

        rec = {
            "idx": i + 1,
            "t0": t0,
            "t1": t1,
            "dur": dur,
            "cmd": ac,
            "wheel": dw,
            "laser": dl,
            "pos_rmse": pos_rmse,
            "yaw_rmse": yaw_rmse,
        }
        by_class.setdefault(label, []).append(rec)

        out("")
        out("--- seg %d: %s (%s)  dur=%.2fs ---" % (i + 1, label, label_cn(label), dur))
        if ac:
            out("  cmd avg: vx=%.4f vy=%.4f wz=%.4f" % ac)
        if label != "stop":
            al = avg_twist_in_range(laser, t0, t1)
            if al:
                out("  laser twist avg: vx=%.4f vy=%.4f wz=%.4f" % al)
        if dw:
            out("  wheel delta: dx=%.3f dy=%.3f dyaw=%.1f deg dist=%.3f m" % (
                dw["dx"], dw["dy"], dw["dyaw_deg"], dw["dist"]))
        if dl:
            out("  laser delta: dx=%.3f dy=%.3f dyaw=%.1f deg dist=%.3f m" % (
                dl["dx"], dl["dy"], dl["dyaw_deg"], dl["dist"]))
        if dw and dl:
            out("  delta diff L-W: ddx=%.3f ddy=%.3f ddyaw=%.1f deg" % (
                dl["dx"] - dw["dx"], dl["dy"] - dw["dy"], dl["dyaw_deg"] - dw["dyaw_deg"]))
        if ex:
            out("  sync err: pos_rmse=%.3f m  yaw_rmse=%.2f deg" % (pos_rmse, yaw_rmse))

    out("")
    out("=== summary by motion class ===")
    out("  label          | segs | total_s | wheel_dist | laser_dist | yaw_W | yaw_L | pos_rmse")
    for label in MOTION_LABELS:
        rows = by_class.get(label, [])
        if not rows or label == "stop":
            continue
        total_s = sum(r["dur"] for r in rows)
        w_dist = sum(r["wheel"]["dist"] for r in rows if r["wheel"])
        l_dist = sum(r["laser"]["dist"] for r in rows if r["laser"])
        w_yaw = sum(abs(r["wheel"]["dyaw_deg"]) for r in rows if r["wheel"])
        l_yaw = sum(abs(r["laser"]["dyaw_deg"]) for r in rows if r["laser"])
        pr = [r["pos_rmse"] for r in rows if not math.isnan(r["pos_rmse"])]
        pr_mean = sum(pr) / len(pr) if pr else float("nan")
        out("  %-14s | %4d | %7.1f | %10.3f | %10.3f | %5.1f | %5.1f | %.3f" % (
            label_cn(label), len(rows), total_s, w_dist, l_dist, w_yaw, l_yaw, pr_mean))

    out("")
    out("=== global sync error (all laser ts) ===")
    ex, ey, eyaw = sync_pose_errors(laser, wheel, laser[0][0], laser[-1][0], w0, l0)
    stat_line("ex (m)", ex)
    stat_line("ey (m)", ey)
    stat_line("eyaw (deg)", eyaw)
    pos = [math.hypot(a, b) for a, b in zip(ex, ey)]
    stat_line("|e| (m)", pos)

    out("")
    out("note: /odom.twist often 0 in xtark_driver; use pose delta + laser twist vs cmd.")

    if args.report:
        with open(args.report, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("  report:", args.report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
