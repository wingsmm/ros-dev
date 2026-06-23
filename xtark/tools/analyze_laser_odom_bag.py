#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Three-way rosbag analysis: /cmd_vel (intent) vs /odom vs /odom_laser.

Segments by motion class (forward/back/strafe/turn/stop), not just motion/stop.
"""

from __future__ import print_function

import argparse
import io
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
MAX_PLOT_POINTS = 1200

try:
    from html import escape as html_escape
except ImportError:
    from cgi import escape as html_escape

try:
    text_type = unicode
except NameError:
    text_type = str


def to_text(value):
    if isinstance(value, text_type):
        return value
    return value.decode("utf-8")

MOTION_LABELS = (
    "stop", "forward", "backward", "strafe_left", "strafe_right",
    "turn_left", "turn_right", "mixed",
)

PLOT_COLORS = (
    "#177e89", "#d1495b", "#edae49", "#30638e",
    "#6a994e", "#8f5d5d", "#7b2cbf", "#495057",
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


def stat_line(name, vals, emit=None):
    if not vals:
        line = "  %s: (no data)" % name
        if emit:
            emit(line)
        else:
            print(line)
        return
    mean = sum(vals) / len(vals)
    line = "  %s: mean=%.4f  max_abs=%.4f  rmse=%.4f  n=%d" % (
        name, mean, max(abs(v) for v in vals), rmse(vals), len(vals))
    if emit:
        emit(line)
    else:
        print(line)


def finite(value):
    return not math.isnan(value) and not math.isinf(value)


def downsample(points, limit=MAX_PLOT_POINTS):
    if len(points) <= limit:
        return points
    step = int(math.ceil(len(points) / float(limit)))
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def series_bounds(series_list):
    xs = []
    ys = []
    for _name, points in series_list:
        for x, y in points:
            if finite(x) and finite(y):
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0.0, 1.0, -1.0, 1.0
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if abs(xmax - xmin) < 1e-9:
        xmax = xmin + 1.0
    if abs(ymax - ymin) < 1e-9:
        pad = max(abs(ymin) * 0.05, 0.1)
        ymin -= pad
        ymax += pad
    else:
        pad = (ymax - ymin) * 0.08
        ymin -= pad
        ymax += pad
    return xmin, xmax, ymin, ymax


def svg_line_chart(title, series_list, y_label):
    width, height = 980, 320
    left, right, top, bottom = 72, 24, 38, 48
    plot_w = width - left - right
    plot_h = height - top - bottom
    clean = [(name, downsample(points)) for name, points in series_list if points]
    xmin, xmax, ymin, ymax = series_bounds(clean)

    def px(x):
        return left + (x - xmin) / (xmax - xmin) * plot_w

    def py(y):
        return top + (ymax - y) / (ymax - ymin) * plot_h

    parts = [
        '<section class="chart-card"><h2>%s</h2>' % html_escape(title),
        '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (
            width, height, html_escape(title)),
        '<rect x="%d" y="%d" width="%d" height="%d" class="plot-bg"/>' % (
            left, top, plot_w, plot_h),
    ]
    for i in range(6):
        gx = left + plot_w * i / 5.0
        gy = top + plot_h * i / 5.0
        xv = xmin + (xmax - xmin) * i / 5.0
        yv = ymax - (ymax - ymin) * i / 5.0
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="grid"/>' % (
            gx, top, gx, top + plot_h))
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="grid"/>' % (
            left, gy, left + plot_w, gy))
        parts.append('<text x="%.1f" y="%d" class="tick" text-anchor="middle">%.1f</text>' % (
            gx, top + plot_h + 20, xv))
        parts.append('<text x="%d" y="%.1f" class="tick" text-anchor="end">%.3g</text>' % (
            left - 8, gy + 4, yv))
    for idx, (name, points) in enumerate(clean):
        color = PLOT_COLORS[idx % len(PLOT_COLORS)]
        coords = " ".join("%.1f,%.1f" % (px(x), py(y)) for x, y in points if finite(x) and finite(y))
        if coords:
            parts.append('<polyline points="%s" fill="none" stroke="%s" class="trace"/>' % (
                coords, color))
    parts.append('<text x="%d" y="%d" class="axis-label" text-anchor="middle">时间（秒）</text>' % (
        left + plot_w / 2, height - 8))
    parts.append('<text transform="translate(16 %d) rotate(-90)" class="axis-label" text-anchor="middle">%s</text>' % (
        top + plot_h / 2, html_escape(y_label)))
    parts.append('</svg><div class="legend">')
    for idx, (name, _points) in enumerate(clean):
        color = PLOT_COLORS[idx % len(PLOT_COLORS)]
        parts.append('<span><i style="background:%s"></i>%s</span>' % (color, html_escape(name)))
    parts.append('</div></section>')
    return "".join(parts)


def svg_xy_chart(title, series_list):
    width, height = 680, 560
    left, right, top, bottom = 70, 24, 38, 54
    plot_w = width - left - right
    plot_h = height - top - bottom
    clean = [(name, downsample(points)) for name, points in series_list if points]
    xmin, xmax, ymin, ymax = series_bounds(clean)
    span = max(xmax - xmin, ymax - ymin, 0.1)
    xmid = (xmin + xmax) / 2.0
    ymid = (ymin + ymax) / 2.0
    xmin, xmax = xmid - span / 2.0, xmid + span / 2.0
    ymin, ymax = ymid - span / 2.0, ymid + span / 2.0

    def px(x):
        return left + (x - xmin) / (xmax - xmin) * plot_w

    def py(y):
        return top + (ymax - y) / (ymax - ymin) * plot_h

    parts = [
        '<section class="chart-card xy-card"><h2>%s</h2>' % html_escape(title),
        '<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (
            width, height, html_escape(title)),
        '<rect x="%d" y="%d" width="%d" height="%d" class="plot-bg"/>' % (
            left, top, plot_w, plot_h),
    ]
    for i in range(6):
        gx = left + plot_w * i / 5.0
        gy = top + plot_h * i / 5.0
        parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" class="grid"/>' % (
            gx, top, gx, top + plot_h))
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="grid"/>' % (
            left, gy, left + plot_w, gy))
    for idx, (name, points) in enumerate(clean):
        color = PLOT_COLORS[idx % len(PLOT_COLORS)]
        coords = " ".join("%.1f,%.1f" % (px(x), py(y)) for x, y in points if finite(x) and finite(y))
        if coords:
            parts.append('<polyline points="%s" fill="none" stroke="%s" class="trace"/>' % (
                coords, color))
            sx, sy = points[0]
            ex, ey = points[-1]
            parts.append('<circle cx="%.1f" cy="%.1f" r="4" fill="%s"/>' % (px(sx), py(sy), color))
            parts.append('<rect x="%.1f" y="%.1f" width="8" height="8" fill="%s"/>' % (
                px(ex) - 4, py(ey) - 4, color))
    parts.append('<text x="%d" y="%d" class="axis-label" text-anchor="middle">X 位移（米）</text>' % (
        left + plot_w / 2, height - 10))
    parts.append('<text transform="translate(16 %d) rotate(-90)" class="axis-label" text-anchor="middle">Y 位移（米）</text>' % (
        top + plot_h / 2))
    parts.append('</svg><div class="legend">')
    for idx, (name, _points) in enumerate(clean):
        color = PLOT_COLORS[idx % len(PLOT_COLORS)]
        parts.append('<span><i style="background:%s"></i>%s</span>' % (color, html_escape(name)))
    parts.append('</div><p class="hint">圆点为起点，方块为终点；每条轨迹均以自己的第一帧进行 SE(2) 对齐。</p></section>')
    return "".join(parts)


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


def relative_pose_series(series, t_ref):
    if not series:
        return []
    x0, y0, yaw0 = pose_xyyaw(series[0][1])
    c = math.cos(yaw0)
    s = math.sin(yaw0)
    result = []
    for ts, msg in series:
        x, y, yaw = pose_xyyaw(msg)
        dx = x - x0
        dy = y - y0
        result.append((ts - t_ref, c * dx + s * dy, -s * dx + c * dy,
                       normalize_angle(yaw - yaw0)))
    return result


def pose_velocity_series(series, t_ref):
    result = []
    for (t0, m0), (t1, m1) in zip(series, series[1:]):
        dt = t1 - t0
        if dt <= 1e-4 or dt > 0.5:
            continue
        x0, y0, yaw0 = pose_xyyaw(m0)
        x1, y1, yaw1 = pose_xyyaw(m1)
        dx = x1 - x0
        dy = y1 - y0
        c = math.cos(yaw0)
        s = math.sin(yaw0)
        vx = (c * dx + s * dy) / dt
        vy = (-s * dx + c * dy) / dt
        wz = normalize_angle(yaw1 - yaw0) / dt
        result.append((t1 - t_ref, vx, vy, wz))
    return result


def relative_error_series(reference, estimate, t_ref):
    if not reference or not estimate:
        return []
    ref_rel = relative_pose_series(reference, t_ref)
    est_rel = relative_pose_series(estimate, t_ref)
    ref_timed = [(row[0] + t_ref, row) for row in ref_rel]
    result = []
    for t_rel, ex, ey, eyaw in est_rel:
        pair = nearest_msg(ref_timed, t_rel + t_ref, PAIR_DT)
        if pair is None:
            continue
        _, ref_row = pair
        _rt, rx, ry, ryaw = ref_row
        result.append((t_rel, math.hypot(ex - rx, ey - ry),
                       math.degrees(normalize_angle(eyaw - ryaw))))
    return result


def cmd_plot_series(cmd, t_ref, index):
    return [(ts - t_ref, cmd_xyz(msg)[index]) for ts, msg in cmd]


def velocity_plot_series(series, t_ref, index):
    return [(row[0], row[index + 1]) for row in pose_velocity_series(series, t_ref)]


def wheel_plot_series(wheel_topics, t_ref):
    result = []
    for wheel in "abcd":
        for suffix, label in (("set", "目标"), ("vel", "反馈")):
            topic = "/xtark/%s%s" % (wheel, suffix)
            points = [(ts - t_ref, float(msg.data)) for ts, msg in wheel_topics.get(topic, [])]
            result.append(("%s 轮%s" % (wheel.upper(), label), points))
    return result


def html_table(rows):
    parts = ['<table><thead><tr><th>数据源</th><th>消息数</th><th>含义</th></tr></thead><tbody>']
    for source, count, meaning in rows:
        parts.append('<tr><td><code>%s</code></td><td>%d</td><td>%s</td></tr>' % (
            html_escape(source), count, html_escape(meaning)))
    parts.append('</tbody></table>')
    return "".join(parts)


def write_html_report(path, bag_path, cmd, raw, fused, laser, wheel_topics):
    all_series = [s for s in (cmd, raw, fused, laser) if s]
    t_ref = min(series[0][0] for series in all_series)
    raw_rel = relative_pose_series(raw, t_ref)
    fused_rel = relative_pose_series(fused, t_ref)
    laser_rel = relative_pose_series(laser, t_ref)

    xy_series = [
        ("编码器 /odom_raw", [(r[1], r[2]) for r in raw_rel]),
        ("融合里程计 /odom", [(r[1], r[2]) for r in fused_rel]),
        ("激光里程计 /odom_laser", [(r[1], r[2]) for r in laser_rel]),
    ]
    vx_series = [
        ("控制命令 /cmd_vel", cmd_plot_series(cmd, t_ref, 0)),
        ("编码器 /odom_raw", velocity_plot_series(raw, t_ref, 0)),
        ("融合里程计 /odom", velocity_plot_series(fused, t_ref, 0)),
        ("激光里程计 /odom_laser", velocity_plot_series(laser, t_ref, 0)),
    ]
    vy_series = [
        ("控制命令 /cmd_vel", cmd_plot_series(cmd, t_ref, 1)),
        ("编码器 /odom_raw", velocity_plot_series(raw, t_ref, 1)),
        ("融合里程计 /odom", velocity_plot_series(fused, t_ref, 1)),
        ("激光里程计 /odom_laser", velocity_plot_series(laser, t_ref, 1)),
    ]
    wz_series = [
        ("控制命令 /cmd_vel", cmd_plot_series(cmd, t_ref, 2)),
        ("编码器 /odom_raw", velocity_plot_series(raw, t_ref, 2)),
        ("融合里程计 /odom", velocity_plot_series(fused, t_ref, 2)),
        ("激光里程计 /odom_laser", velocity_plot_series(laser, t_ref, 2)),
    ]
    yaw_series = [
        ("编码器 /odom_raw", [(r[0], math.degrees(r[3])) for r in raw_rel]),
        ("融合里程计 /odom", [(r[0], math.degrees(r[3])) for r in fused_rel]),
        ("激光里程计 /odom_laser", [(r[0], math.degrees(r[3])) for r in laser_rel]),
    ]
    raw_err = relative_error_series(raw, laser, t_ref)
    fused_err = relative_error_series(fused, laser, t_ref)
    pos_error_series = [
        ("激光 - 编码器", [(r[0], r[1]) for r in raw_err]),
        ("激光 - 融合里程计", [(r[0], r[1]) for r in fused_err]),
    ]
    yaw_error_series = [
        ("激光 - 编码器", [(r[0], r[2]) for r in raw_err]),
        ("激光 - 融合里程计", [(r[0], r[2]) for r in fused_err]),
    ]
    wheel_series = wheel_plot_series(wheel_topics, t_ref)

    rows = [
        ("/cmd_vel", len(cmd), "上层运动意图，不是真值"),
        ("/odom_raw", len(raw), "编码器原始里程计"),
        ("/odom", len(fused), "xtark_bringup 中编码器与 IMU 的融合里程计"),
        ("/odom_laser", len(laser), "RF2O 激光里程计"),
    ]
    for topic in sorted(wheel_topics):
        rows.append((topic, len(wheel_topics[topic]), "下位机车轮目标速度或反馈速度"))

    charts = [
        svg_xy_chart("SE(2) 对齐后的 XY 轨迹", xy_series),
        svg_line_chart("前进速度跟随", vx_series, "前进速度 vx（米/秒）"),
        svg_line_chart("横移速度跟随", vy_series, "横移速度 vy（米/秒）"),
        svg_line_chart("旋转速度跟随", wz_series, "角速度 wz（弧度/秒）"),
        svg_line_chart("相对航向角", yaw_series, "航向角 yaw（度）"),
        svg_line_chart("位置一致性误差", pos_error_series, "位置差（米）"),
        svg_line_chart("航向角一致性误差", yaw_error_series, "角度差（度）"),
    ]
    if any(points for _name, points in wheel_series):
        charts.append(svg_line_chart("四轮目标速度与反馈速度", wheel_series, "下位机速度单位"))

    css = """
    :root{--ink:#19323c;--muted:#61747c;--paper:#f4f0e8;--card:#fffdf8;--line:#d8d1c3;--accent:#d1495b}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#e8efe9,#f4f0e8 42%,#efe4d5);color:var(--ink);font-family:Georgia,'Times New Roman',serif}
    main{max-width:1120px;margin:0 auto;padding:38px 24px 64px}header{border-left:8px solid var(--accent);padding:8px 0 8px 20px;margin-bottom:24px}h1{margin:0 0 8px;font-size:34px}h2{margin:0 0 12px;font-size:19px}p{line-height:1.55}.subtitle,.hint{color:var(--muted)}.notice{background:#19323c;color:#fffdf8;padding:15px 18px;border-radius:8px;margin:18px 0 26px}
    .chart-card,.data-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0;box-shadow:0 8px 24px rgba(25,50,60,.08);overflow:auto}.xy-card{max-width:760px}
    svg{display:block;width:100%;min-width:620px}.plot-bg{fill:#faf8f2;stroke:var(--line)}.grid{stroke:#ded9cf;stroke-width:1}.trace{stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round}.tick{font:12px Consolas,monospace;fill:var(--muted)}.axis-label{font:13px Georgia,serif;fill:var(--ink)}
    .legend{display:flex;flex-wrap:wrap;gap:12px 18px;font:13px Consolas,monospace}.legend span{display:flex;align-items:center;gap:6px}.legend i{width:18px;height:4px;border-radius:3px}table{width:100%;border-collapse:collapse;font-family:Consolas,monospace;font-size:13px}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line)}th{background:#f0ece3}code{font-family:Consolas,monospace}
    """
    body = "".join(charts)
    document = """<!doctype html><html><head><meta charset="utf-8"><title>Xtark 里程计对比报告</title><style>%s</style></head><body><main>
    <header><h1>Xtark 里程计对比报告</h1><p class="subtitle">%s</p></header>
    <div class="notice"><strong>如何理解：</strong>/cmd_vel 是控制意图；编码器、融合里程计和激光里程计都是估计值。曲线彼此接近，只能说明它们一致；没有独立外部真值时，不能证明真实物理精度。</div>
    <section class="data-card"><h2>已记录的数据源</h2>%s</section>%s
    </main></body></html>""" % (css, html_escape(bag_path), html_table(rows), body)
    with io.open(path, "w", encoding="utf-8") as report:
        report.write(to_text(document))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bag")
    parser.add_argument("--report", default="")
    parser.add_argument("--html-report", default="",
                        help="write a self-contained HTML/SVG visual report")
    args = parser.parse_args()

    bag = rosbag.Bag(args.bag)
    cmd = []
    fused = []
    raw = []
    laser = []
    wheel_topic_names = ["/xtark/%s%s" % (wheel, suffix)
                         for wheel in "abcd" for suffix in ("set", "vel")]
    wheel_topics = dict((topic, []) for topic in wheel_topic_names)
    read_topics = ["/cmd_vel", "/odom_raw", "/odom", "/odom_laser"] + wheel_topic_names
    for topic, msg, t in bag.read_messages(topics=read_topics):
        ts = t.to_sec()
        if topic == "/cmd_vel":
            cmd.append((ts, msg))
        elif topic == "/odom_raw":
            raw.append((ts, msg))
        elif topic == "/odom":
            fused.append((ts, msg))
        elif topic == "/odom_laser":
            laser.append((ts, msg))
        elif topic in wheel_topics:
            wheel_topics[topic].append((ts, msg))
    bag.close()

    lines = []

    def out(s=""):
        lines.append(s)
        print(s)

    out("=== bag ===")
    out("  path: %s" % args.bag)
    out("  cmd_vel: %d  raw encoder /odom_raw: %d  fused /odom: %d  laser /odom_laser: %d" % (
        len(cmd), len(raw), len(fused), len(laser)))
    out("  wheel set/feedback: %d" % sum(len(v) for v in wheel_topics.values()))

    if not cmd or not fused or not laser:
        out("[ERR] missing required topics: /cmd_vel, /odom, or /odom_laser")
        return 1

    w0 = pose_xyyaw(fused[0][1])
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
        dw = pose_delta_in_range(fused, t0, t1)
        dr = pose_delta_in_range(raw, t0, t1)
        dl = pose_delta_in_range(laser, t0, t1)
        ex, ey, eyaw = sync_pose_errors(laser, fused, t0, t1, w0, l0)
        pos_rmse = rmse([math.hypot(a, b) for a, b in zip(ex, ey)]) if ex else float("nan")
        yaw_rmse = rmse(eyaw) if eyaw else float("nan")

        rec = {
            "idx": i + 1,
            "t0": t0,
            "t1": t1,
            "dur": dur,
            "cmd": ac,
            "wheel": dw,
            "raw": dr,
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
            out("  fused delta: dx=%.3f dy=%.3f dyaw=%.1f deg dist=%.3f m" % (
                dw["dx"], dw["dy"], dw["dyaw_deg"], dw["dist"]))
        if dr:
            out("  raw encoder delta: dx=%.3f dy=%.3f dyaw=%.1f deg dist=%.3f m" % (
                dr["dx"], dr["dy"], dr["dyaw_deg"], dr["dist"]))
        if dl:
            out("  laser delta: dx=%.3f dy=%.3f dyaw=%.1f deg dist=%.3f m" % (
                dl["dx"], dl["dy"], dl["dyaw_deg"], dl["dist"]))
        if dw and dl:
            out("  delta diff laser-fused: ddx=%.3f ddy=%.3f ddyaw=%.1f deg" % (
                dl["dx"] - dw["dx"], dl["dy"] - dw["dy"], dl["dyaw_deg"] - dw["dyaw_deg"]))
        if ex:
            out("  sync err: pos_rmse=%.3f m  yaw_rmse=%.2f deg" % (pos_rmse, yaw_rmse))

    out("")
    out("=== summary by motion class ===")
    out("  label          | segs | total_s | fused_dist | laser_dist | yaw_F | yaw_L | pos_rmse")
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
    out("=== global sync error: laser vs fused /odom (all laser ts) ===")
    ex, ey, eyaw = sync_pose_errors(laser, fused, laser[0][0], laser[-1][0], w0, l0)
    stat_line("ex (m)", ex, out)
    stat_line("ey (m)", ey, out)
    stat_line("eyaw (deg)", eyaw, out)
    pos = [math.hypot(a, b) for a, b in zip(ex, ey)]
    stat_line("|e| (m)", pos, out)

    if raw:
        out("")
        out("=== global sync error: laser vs raw encoder /odom_raw ===")
        r0 = pose_xyyaw(raw[0][1])
        ex, ey, eyaw = sync_pose_errors(laser, raw, laser[0][0], laser[-1][0], r0, l0)
        stat_line("ex (m)", ex, out)
        stat_line("ey (m)", ey, out)
        stat_line("eyaw (deg)", eyaw, out)
        stat_line("|e| (m)", [math.hypot(a, b) for a, b in zip(ex, ey)], out)
    else:
        out("")
        out("[WARN] /odom_raw missing: cannot separate encoder from encoder+IMU fusion")

    out("")
    out("note: /odom.twist often 0 in xtark_driver; use pose delta + laser twist vs cmd.")

    if args.report:
        with io.open(args.report, "w", encoding="utf-8") as f:
            f.write(to_text("\n".join(lines) + "\n"))
        print("  report:", args.report)

    if args.html_report:
        write_html_report(args.html_report, args.bag, cmd, raw, fused, laser, wheel_topics)
        print("  html report:", args.html_report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
